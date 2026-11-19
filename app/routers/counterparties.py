"""Справочник контрагентов (CRUD)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Counterparty, User
from ..schemas import CounterpartyIn, CounterpartyOut
from ..security import current_user

router = APIRouter(prefix="/api/counterparties", tags=["counterparties"])


def _get_owned(db: Session, user: User, cp_id: int) -> Counterparty:
    cp = db.get(Counterparty, cp_id)
    if not cp or cp.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Контрагент не найден")
    return cp


@router.get("", response_model=list[CounterpartyOut])
def list_counterparties(include_inactive: bool = False,
                        user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    q = db.query(Counterparty).filter(Counterparty.owner_id == user.id)
    if not include_inactive:
        q = q.filter(Counterparty.is_active.is_(True))
    return q.order_by(Counterparty.name).all()


@router.post("", response_model=CounterpartyOut, status_code=201)
def create_counterparty(data: CounterpartyIn, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    cp = Counterparty(owner_id=user.id, **data.model_dump())
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


@router.put("/{cp_id}", response_model=CounterpartyOut)
def update_counterparty(cp_id: int, data: CounterpartyIn,
                        user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    cp = _get_owned(db, user, cp_id)
    for k, v in data.model_dump().items():
        setattr(cp, k, v)
    db.commit()
    db.refresh(cp)
    return cp


@router.delete("/{cp_id}")
def delete_counterparty(cp_id: int, hard: bool = False,
                        user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    cp = _get_owned(db, user, cp_id)
    if hard:
        db.delete(cp)
    else:
        cp.is_active = False
    db.commit()
    return {"ok": True}
