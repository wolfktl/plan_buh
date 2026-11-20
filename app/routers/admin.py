"""Администрирование пользователей (только для роли admin)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import security
from ..database import get_db
from ..models import User
from ..schemas import (AdminPasswordReset, AdminUserCreate, AdminUserOut,
                       AdminUserUpdate)
from ..security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


def _active_admins(db: Session) -> int:
    return db.query(func.count(User.id)).filter(
        User.role == "admin", User.is_active.is_(True)).scalar() or 0


def _get(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return u


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=AdminUserOut, status_code=201)
def create_user(data: AdminUserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username.strip()).first():
        raise HTTPException(status_code=409, detail="Логин уже занят")
    u = User(username=data.username.strip(),
             password_hash=security.hash_password(data.password),
             role=data.role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.put("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: int, data: AdminUserUpdate,
                me: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, user_id)

    # Нельзя снять последнего администратора (разжалование или деактивация).
    removing_admin = (
        (data.role is not None and data.role != "admin" and u.role == "admin")
        or (data.is_active is False and u.role == "admin" and u.is_active)
    )
    if removing_admin and _active_admins(db) <= 1:
        raise HTTPException(status_code=400,
                            detail="Нельзя снять права у последнего администратора")
    if data.is_active is False and u.id == me.id:
        raise HTTPException(status_code=400, detail="Нельзя деактивировать самого себя")

    if data.role is not None:
        u.role = data.role
    if data.is_active is not None:
        u.is_active = data.is_active
    db.commit()
    db.refresh(u)
    return u


@router.post("/users/{user_id}/password")
def reset_password(user_id: int, data: AdminPasswordReset,
                   db: Session = Depends(get_db)):
    u = _get(db, user_id)
    u.password_hash = security.hash_password(data.password)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-2fa")
def reset_2fa(user_id: int, db: Session = Depends(get_db)):
    """Сбросить 2FA пользователю (например, при утере устройства)."""
    u = _get(db, user_id)
    u.totp_enabled = False
    u.totp_secret = None
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, me: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    u = _get(db, user_id)
    if u.id == me.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    if u.role == "admin" and _active_admins(db) <= 1:
        raise HTTPException(status_code=400,
                            detail="Нельзя удалить последнего администратора")
    db.delete(u)
    db.commit()
    return {"ok": True}
