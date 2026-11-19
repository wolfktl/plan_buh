"""Планировщик: события календаря, отметки выполнения, свои задачи."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..calendar_gen import applies_to, get_events
from ..database import get_db
from ..models import Completion, Counterparty, CustomTask, User
from ..schemas import CompletionIn, CustomTaskIn, CustomTaskOut
from ..security import current_user

router = APIRouter(prefix="/api", tags=["planner"])


def _owned_cp(db: Session, user: User, cp_id: int) -> Counterparty:
    cp = db.get(Counterparty, cp_id)
    if not cp or cp.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Контрагент не найден")
    return cp


@router.get("/events")
def events(counterparty_id: int | None = None, year: int = 2026,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Налоговый календарь. Если задан контрагент — с отметками, признаком
    применимости к его режиму и его собственными задачами."""
    base = get_events(year)
    cp = None
    done_keys: set[str] = set()
    custom: list[dict] = []

    if counterparty_id is not None:
        cp = _owned_cp(db, user, counterparty_id)
        done_keys = {c.event_key for c in
                     db.query(Completion).filter(
                         Completion.counterparty_id == cp.id).all()}
        for t in db.query(CustomTask).filter(
                CustomTask.counterparty_id == cp.id).all():
            custom.append({
                "key": f"c{t.id}", "date": t.due_date.isoformat(),
                "title": t.title, "cat": "custom", "type": "not",
                "applies": ["all"], "note": t.note or "", "moved": False,
                "custom": True, "done": t.done,
            })

    out = []
    for e in base:
        item = dict(e)
        item["custom"] = False
        item["done"] = e["key"] in done_keys
        if cp is not None:
            item["applicable"] = applies_to(e, cp.form, cp.tax_system, cp.has_employees)
        else:
            item["applicable"] = True
        out.append(item)
    out.extend(custom)
    out.sort(key=lambda x: (x["date"], x.get("type", "")))

    return {
        "year": year,
        "counterparty_id": counterparty_id,
        "events": out,
    }


@router.post("/completions")
def set_completion(data: CompletionIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Отметить/снять отметку выполнения события для контрагента."""
    cp = _owned_cp(db, user, data.counterparty_id)

    # Своя задача (ключ вида c<ID>) — переключаем её флаг done.
    if data.event_key.startswith("c"):
        try:
            tid = int(data.event_key[1:])
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный ключ")
        t = db.get(CustomTask, tid)
        if not t or t.counterparty_id != cp.id:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        t.done = data.done
        db.commit()
        return {"ok": True}

    existing = db.query(Completion).filter(
        Completion.counterparty_id == cp.id,
        Completion.event_key == data.event_key).first()
    if data.done and not existing:
        db.add(Completion(counterparty_id=cp.id, event_key=data.event_key))
    elif not data.done and existing:
        db.delete(existing)
    db.commit()
    return {"ok": True}


@router.post("/custom-tasks", response_model=CustomTaskOut, status_code=201)
def add_custom_task(data: CustomTaskIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    _owned_cp(db, user, data.counterparty_id)
    t = CustomTask(counterparty_id=data.counterparty_id, title=data.title,
                   due_date=data.due_date, note=data.note)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/custom-tasks/{task_id}")
def delete_custom_task(task_id: int, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    t = db.get(CustomTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    cp = db.get(Counterparty, t.counterparty_id)
    if not cp or cp.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    db.delete(t)
    db.commit()
    return {"ok": True}
