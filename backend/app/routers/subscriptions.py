from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import economy, models
from ..auth import authenticate
from ..database import get_db
from ..schemas import UserOut
from .common import serialize_user

router = APIRouter(prefix="/api", tags=["subscriptions"])


@router.get("/tiers")
def tiers():
    return [
        {"tier": t, "name": cfg["name"], "price": cfg["price"], "daily_limit": cfg["daily_limit"]}
        for t, cfg in economy.TIERS.items()
    ]


@router.post("/subscribe/{tier}", response_model=UserOut)
def subscribe(
    tier: int,
    user: models.User = Depends(authenticate),
    db: Session = Depends(get_db),
):
    if tier not in economy.TIERS:
        raise HTTPException(status_code=400, detail="Неизвестный этап")

    price = economy.TIERS[tier]["price"]
    if user.balance < price:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно средств: нужно {price} УЕ, на балансе {round(user.balance, 2)} УЕ",
        )

    is_first = (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == user.id, models.Transaction.type == "subscription")
        .first()
        is None
    )

    user.balance -= price
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    base = user.tier_expires_at if (user.tier_expires_at and user.tier_expires_at > now) else now
    user.tier = tier
    user.tier_expires_at = base + timedelta(days=30)
    db.add(
        models.Transaction(
            user_id=user.id,
            type="subscription",
            amount=-price,
            note=f"Подписка: {economy.TIERS[tier]['name']} (DEMO)",
        )
    )

    # Referral bonus on the referred user's first subscription.
    if is_first and user.referred_by:
        referrer = (
            db.query(models.User).filter(models.User.telegram_id == user.referred_by).first()
        )
        if referrer:
            bonus = round(price * economy.REFERRAL_RATE, 2)
            referrer.balance += bonus
            referrer.referral_earnings += bonus
            db.add(
                models.Transaction(
                    user_id=referrer.id,
                    type="referral_bonus",
                    amount=bonus,
                    note=f"Реферальный бонус 15% от подписки @{user.username or user.telegram_id}",
                )
            )

    db.commit()
    db.refresh(user)
    return serialize_user(db, user)
