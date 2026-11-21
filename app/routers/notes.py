"""Личные заметки пользователя в календаре (с поддержкой повторов)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Note, NoteDone, User
from ..schemas import NoteIn, NoteOut, OccurrenceIn
from ..security import current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _owned(db: Session, user: User, note_id: int) -> Note:
    n = db.get(Note, note_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Заметка не найдена")
    return n


def _to_out(n: Note, done_dates: list[date]) -> NoteOut:
    out = NoteOut.model_validate(n)
    out.done_dates = done_dates
    return out


@router.get("", response_model=list[NoteOut])
def list_notes(date_from: date | None = None, date_to: date | None = None,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    notes = db.query(Note).filter(Note.user_id == user.id).order_by(
        Note.note_date, Note.id).all()
    # отметки выполнения вхождений (для повторяющихся)
    ids = [n.id for n in notes]
    done_map: dict[int, list[date]] = {}
    if ids:
        for d in db.query(NoteDone).filter(NoteDone.note_id.in_(ids)).all():
            done_map.setdefault(d.note_id, []).append(d.occ_date)

    result = []
    for n in notes:
        recurring = n.repeat and n.repeat != "none"
        # разовые — фильтруем по диапазону, если задан; повторяющиеся — всегда
        if not recurring:
            if date_from and n.note_date < date_from:
                continue
            if date_to and n.note_date > date_to:
                continue
        result.append(_to_out(n, done_map.get(n.id, [])))
    return result


@router.post("", response_model=NoteOut, status_code=201)
def create_note(data: NoteIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    n = Note(user_id=user.id, **data.model_dump())
    db.add(n)
    db.commit()
    db.refresh(n)
    return _to_out(n, [])


@router.put("/{note_id}", response_model=NoteOut)
def update_note(note_id: int, data: NoteIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    n = _owned(db, user, note_id)
    for k, v in data.model_dump().items():
        setattr(n, k, v)
    if n.remind_at is not None:
        n.remind_sent = False
    db.commit()
    db.refresh(n)
    dates = [d.occ_date for d in db.query(NoteDone).filter(
        NoteDone.note_id == n.id).all()]
    return _to_out(n, dates)


@router.post("/{note_id}/occurrence")
def set_occurrence(note_id: int, data: OccurrenceIn,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Отметить/снять выполнение конкретного вхождения повторяющейся заметки."""
    n = _owned(db, user, note_id)
    existing = db.query(NoteDone).filter(
        NoteDone.note_id == n.id, NoteDone.occ_date == data.occ_date).first()
    if data.done and not existing:
        db.add(NoteDone(note_id=n.id, occ_date=data.occ_date))
    elif not data.done and existing:
        db.delete(existing)
    db.commit()
    return {"ok": True}


@router.delete("/{note_id}")
def delete_note(note_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    n = _owned(db, user, note_id)
    db.delete(n)
    db.commit()
    return {"ok": True}
