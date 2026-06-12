from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import economy, models
from ..auth import authenticate
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: models.User = Depends(authenticate)) -> models.User:
    if user.telegram_id not in settings.admin_id_set:
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return user


def _log(db: Session, admin_id: int, action: str, detail: str):
    db.add(models.AdminLog(admin_id=admin_id, action=action, detail=detail))


@router.get("/stats")
def stats(admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    total_users = db.query(func.count(models.User.id)).scalar()
    by_tier = {
        t: db.query(func.count(models.User.id)).filter(models.User.tier == t).scalar()
        for t in economy.TIERS
    }
    day_start = economy.utc_day_start()
    trades_today = (
        db.query(func.count(models.Trade.id))
        .filter(models.Trade.created_at >= day_start)
        .scalar()
    )
    return {
        "demo": True,
        "total_users": total_users,
        "active_by_tier": by_tier,
        "trades_today": trades_today,
        "note": "Все суммы виртуальные (УЕ). Реальный оборот отсутствует.",
    }


@router.get("/users")
def list_users(
    q: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.User)
    if q:
        if q.isdigit():
            query = query.filter(models.User.telegram_id == int(q))
        else:
            query = query.filter(models.User.username.ilike(f"%{q}%"))
    rows = query.order_by(models.User.id.desc()).offset(offset).limit(limit).all()
    return [
        {
            "telegram_id": u.telegram_id,
            "username": u.username,
            "tier": u.tier,
            "balance": round(u.balance, 2),
            "total_trades": u.total_trades,
            "level": u.level,
        }
        for u in rows
    ]


@router.post("/users/{telegram_id}/adjust")
def adjust_balance(
    telegram_id: int,
    amount: float,
    note: str = "Корректировка администратором",
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.balance += amount
    db.add(
        models.Transaction(user_id=user.id, type="admin_adjust", amount=amount, note=note)
    )
    _log(db, admin.telegram_id, "adjust_balance", f"{telegram_id}: {amount} УЕ ({note})")
    db.commit()
    return {"ok": True, "balance": round(user.balance, 2)}


@router.post("/users/{telegram_id}/set_tier")
def set_tier(
    telegram_id: int,
    tier: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if tier not in economy.TIERS:
        raise HTTPException(status_code=400, detail="Неизвестный этап")
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.tier = tier
    _log(db, admin.telegram_id, "set_tier", f"{telegram_id} -> tier {tier}")
    db.commit()
    return {"ok": True, "tier": tier}


@router.get("/logs")
def logs(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.AdminLog)
        .order_by(models.AdminLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "admin_id": r.admin_id,
            "action": r.action,
            "detail": r.detail,
            "created_at": r.created_at,
        }
        for r in rows
    ]
