"""Личные заметки пользователя в календаре."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Note, User
from ..schemas import NoteIn, NoteOut
from ..security import current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _owned(db: Session, user: User, note_id: int) -> Note:
    n = db.get(Note, note_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Заметка не найдена")
    return n


@router.get("", response_model=list[NoteOut])
def list_notes(date_from: date | None = None, date_to: date | None = None,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Note).filter(Note.user_id == user.id)
    if date_from:
        q = q.filter(Note.note_date >= date_from)
    if date_to:
        q = q.filter(Note.note_date <= date_to)
    return q.order_by(Note.note_date, Note.id).all()


@router.post("", response_model=NoteOut, status_code=201)
def create_note(data: NoteIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    n = Note(user_id=user.id, **data.model_dump())
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.put("/{note_id}", response_model=NoteOut)
def update_note(note_id: int, data: NoteIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    n = _owned(db, user, note_id)
    for k, v in data.model_dump().items():
        setattr(n, k, v)
    # при (пере)установке напоминания — разрешаем повторную отправку
    if n.remind_at is not None:
        n.remind_sent = False
    db.commit()
    db.refresh(n)
    return n


@router.delete("/{note_id}")
def delete_note(note_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    n = _owned(db, user, note_id)
    db.delete(n)
    db.commit()
    return {"ok": True}
