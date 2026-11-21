"""Генерация налогового календаря РФ для произвольного года.

Правила ЕНС стабильны из года в год (отчётность до 25-го, уплата до 28-го,
НДФЛ по двум периодам и т.д.). Конкретные даты вычисляются с автоматическим
переносом срока на ближайший рабочий день (п. 7 ст. 6.1 НК РФ) по
производственному календарю соответствующего года.

Производственный календарь строится из федеральных нерабочих праздничных дней
(ст. 112 ТК РФ) с переносом праздника, выпавшего на выходной, на следующий
рабочий день. Ежегодные правительственные переносы выходных (длинные каникулы)
задаются таблицей EXTRA_NONWORKING для известных лет; для 2026 она выверена по
Постановлению Правительства РФ № 1466 от 24.09.2025.

Поле ``applies`` — набор условий применимости события к контрагенту:
  osno / usn / employees / ip / all.
"""
import calendar
from datetime import date, timedelta

# Федеральные нерабочие праздничные дни (месяц, день) — одинаковы каждый год.
FEDERAL_HOLIDAYS = [
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),  # новогодние + Рождество
    (2, 23),   # День защитника Отечества
    (3, 8),    # Международный женский день
    (5, 1),    # Праздник Весны и Труда
    (5, 9),    # День Победы
    (6, 12),   # День России
    (11, 4),   # День народного единства
]

# Дополнительные нерабочие дни из-за правительственных переносов (по годам).
# Выверено для 2026; для других лет — добавляйте по мере выхода постановлений.
EXTRA_NONWORKING = {
    2026: {"2026-01-09", "2026-12-31"},
}

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
VZNOS_NOTICE_MONTHS = {1, 2, 4, 5, 7, 8, 10, 11}  # 1-й и 2-й месяцы кварталов

_HCACHE: dict[int, set] = {}


def _compute_holidays(year: int) -> set:
    """Нерабочие дни года: федеральные праздники + перенос праздников,
    выпавших на выходной (ст. 112 ТК РФ), + известные правительственные переносы."""
    base = {date(year, m, d).isoformat() for (m, d) in FEDERAL_HOLIDAYS}
    extra = set()
    for iso in list(base):
        dt = date.fromisoformat(iso)
        if dt.weekday() >= 5:  # праздник на выходной — переносим на рабочий день
            nd = dt + timedelta(days=1)
            while nd.weekday() >= 5 or nd.isoformat() in base or nd.isoformat() in extra:
                nd += timedelta(days=1)
            extra.add(nd.isoformat())
    return base | extra | EXTRA_NONWORKING.get(year, set())


def holidays(year: int) -> set:
    if year not in _HCACHE:
        _HCACHE[year] = _compute_holidays(year)
    return _HCACHE[year]


def _is_non_working(d: date) -> bool:
    if d.weekday() >= 5:  # 5=сб, 6=вс
        return True
    return d.isoformat() in holidays(d.year)


def adjust(y: int, m: int, d: int) -> tuple[date, bool]:
    """Вернуть (дата с переносом на рабочий день, был_ли_перенос). m — 0-индекс."""
    cur = date(y, m + 1, d)
    moved = False
    while _is_non_working(cur):
        cur += timedelta(days=1)
        moved = True
    return cur, moved


def _last_day(year: int, month0: int) -> int:
    return calendar.monthrange(year, month0 + 1)[1]


def build_events(year: int) -> list[dict]:
    events: list[dict] = []
    counter = {"n": 0}

    def add(y, m, d, title, cat, type_, applies, note=""):
        dt, moved = adjust(y, m, d)
        counter["n"] += 1
        events.append({
            "key": f"b{counter['n']}",
            "date": dt.isoformat(),
            "title": title, "cat": cat, "type": type_,
            "applies": applies, "note": note, "moved": moved,
        })

    Y = year
    yp = year - 1  # предыдущий год (за него сдаётся годовая отчётность в Y)

    # ---- Ежемесячные события ----
    for m in range(12):
        prev_m = (m + 11) % 12
        prev = MONTHS_GEN[prev_m]
        cur = MONTHS_GEN[m]
        last_prev = _last_day(Y if m != 0 else Y - 1, prev_m)

        if m != 0:
            add(Y, m, 3, f"Уведомление по НДФЛ (за 23–{last_prev} {prev})",
                "ndfl", "not", ["employees"],
                f"НДФЛ, удержанный с 23-го по последнее число {prev}")
            add(Y, m, 5, f"Уплата НДФЛ (за 23–конец {prev})",
                "ndfl", "pay", ["employees"],
                f"Перечисление налога за второй период {prev}")

        add(Y, m, 25, f"Уведомление по НДФЛ (за 1–22 {cur})",
            "ndfl", "not", ["employees"],
            f"НДФЛ, удержанный с 1-го по 22-е число {cur}")
        add(Y, m, 25, f"Персонифицированные сведения о физлицах (за {prev})",
            "otchet", "rep", ["employees"],
            "Ежемесячно в СФР за предыдущий месяц")
        if m in VZNOS_NOTICE_MONTHS:
            add(Y, m, 25, f"Уведомление по страховым взносам (за {prev})",
                "vznos", "not", ["employees"],
                "В 3-й месяц квартала заменяется РСВ")
        add(Y, m, 28, "Уплата ЕНП — единый налоговый платёж",
            "vznos", "pay", ["all"],
            f"НДФЛ (1–22 {cur}), взносы за {prev}, авансы по налогам")

    # ---- Квартальная отчётность (25-е месяца после квартала) ----
    q_month = [3, 6, 9]          # апрель, июль, октябрь
    q_label = ["I квартал", "полугодие", "9 месяцев"]
    q_rim = ["I", "II", "III"]
    for q in range(3):
        qm, lbl = q_month[q], q_label[q]
        add(Y, qm, 25, f"Декларация по НДС ({q_rim[q]} квартал {Y})",
            "nds", "rep", ["osno"],
            "Уплата — тремя равными частями до 28-го числа каждого из 3 следующих месяцев")
        add(Y, qm, 25, f"РСВ — расчёт по страховым взносам ({lbl} {Y})",
            "vznos", "rep", ["employees"], "Все работодатели")
        add(Y, qm, 25, f"6-НДФЛ ({lbl} {Y})", "ndfl", "rep", ["employees"],
            "Расчёт сумм НДФЛ")
        add(Y, qm, 25, f"Декларация по налогу на прибыль ({lbl} {Y})",
            "pribyl", "rep", ["osno"], "При ежеквартальной уплате авансов")
        add(Y, qm, 25, f"ЕФС-1, раздел 2 — взносы на травматизм ({lbl} {Y})",
            "vznos", "rep", ["employees"], "В СФР ежеквартально")
        add(Y, qm, 25, f"Уведомление по авансу УСН ({lbl} {Y})",
            "usn", "not", ["usn"], "Аванс по УСН за квартал")
        add(Y, qm, 28, f"Уплата аванса по УСН ({lbl} {Y})",
            "usn", "pay", ["usn"], "Авансовый платёж по УСН")

    # ---- Годовая отчётность за предыдущий год (yp), сдаётся в Y ----
    add(Y, 0, 25, f"Декларация по НДС за IV квартал {yp}", "nds", "rep", ["osno"],
        "Годовое закрытие НДС")
    add(Y, 0, 25, f"РСВ за {yp} год", "vznos", "rep", ["employees"], "Годовой расчёт")
    add(Y, 0, 25, f"Персонифицированные сведения за декабрь {yp}", "otchet", "rep",
        ["employees"], "В СФР")
    add(Y, 0, 25, f"ЕФС-1, раздел 2 за {yp} (травматизм)", "vznos", "rep",
        ["employees"], "Годовой")
    add(Y, 0, 25, f"ЕФС-1, подраздел 1.2 (стаж) за {yp}", "otchet", "rep",
        ["employees"], "Сведения о стаже — ежегодно в СФР")
    add(Y, 1, 25, f"6-НДФЛ за {yp} год", "ndfl", "rep", ["employees"],
        "Годовой расчёт со справками о доходах")
    add(Y, 2, 25, f"Декларация по налогу на прибыль за {yp}", "pribyl", "rep",
        ["osno"], "Годовая декларация")
    add(Y, 2, 25, f"Декларация по УСН за {yp} — организации", "usn", "rep", ["usn"],
        "Для ООО на УСН")
    add(Y, 2, 31, f"Бухгалтерская (финансовая) отчётность за {yp}", "otchet", "rep",
        ["all"], "Баланс и приложения — в ФНС и ГИРБО")
    add(Y, 3, 15, "Подтверждение основного вида деятельности в СФР", "otchet", "rep",
        ["employees"], "Для тарифа взносов на травматизм")
    add(Y, 3, 25, f"Декларация по УСН за {yp} — ИП", "usn", "rep", ["usn", "ip"],
        "Для ИП на УСН")
    add(Y, 3, 30, f"Декларация 3-НДФЛ за {yp}", "ipself", "rep", ["ip"],
        "ИП на ОСНО и физлица, декларирующие доходы")

    # ---- Платежи по итогам года и взносы ИП ----
    add(Y, 2, 28, f"Уплата УСН за {yp} — организации", "usn", "pay", ["usn"],
        "Годовой налог по УСН")
    add(Y, 3, 28, f"Уплата УСН за {yp} — ИП", "usn", "pay", ["usn", "ip"],
        "Годовой налог по УСН для ИП")
    add(Y, 2, 28, f"Уплата налога на прибыль за {yp}", "pribyl", "pay", ["osno"],
        "Годовой налог")
    add(Y, 6, 1, f"Взносы ИП за себя: 1% с дохода свыше 300 000 ₽ за {yp}",
        "ipself", "pay", ["ip"], "Срок — 1 июля")
    add(Y, 6, 15, f"Уплата НДФЛ по 3-НДФЛ за {yp} (ИП на ОСНО)", "ipself", "pay",
        ["ip"], "Итоговый НДФЛ предпринимателя")
    add(Y, 11, 28, f"Фиксированные взносы ИП за себя за {Y}", "ipself", "pay",
        ["ip"], "Срок — 28 декабря; сумму уточняйте на текущий год")

    events.sort(key=lambda e: (e["date"], e["type"]))
    return events


def applies_to(event: dict, form: str, tax_system: str, has_employees: bool) -> bool:
    a = event["applies"]
    if "all" in a:
        return True
    ok = False
    if "osno" in a and tax_system == "osno":
        ok = True
    if "usn" in a and tax_system == "usn":
        ok = True
    if "employees" in a and has_employees:
        ok = True
    if "ip" in a and form == "ip":
        ok = True
    return ok


_CACHE: dict[int, list[dict]] = {}


def get_events(year: int = 2026) -> list[dict]:
    if year not in _CACHE:
        _CACHE[year] = build_events(year)
    return _CACHE[year]
