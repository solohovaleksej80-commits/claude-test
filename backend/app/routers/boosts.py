from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import economy, models
from ..auth import authenticate
from ..database import get_db
from ..schemas import UserOut
from .common import serialize_user

router = APIRouter(prefix="/api", tags=["boosts"])


@router.get("/boosts/price")
def boost_price(user: models.User = Depends(authenticate), db: Session = Depends(get_db)):
    return {
        "next_price": economy.next_boost_price(db, user),
        "bought_today": economy.boosts_bought_today(db, user.id),
        "weekly_cap": 3 * economy.daily_trade_limit(user),
        "bought_this_week": economy.boosts_bought_this_week(db, user.id),
    }


@router.post("/boosts/buy", response_model=UserOut)
def buy_boost(user: models.User = Depends(authenticate), db: Session = Depends(get_db)):
    if user.tier < 2:
        raise HTTPException(status_code=400, detail="Бусты доступны с Этапа 2")

    # Anti-abuse: weekly cap = 3 × daily limit.
    weekly_cap = 3 * economy.daily_trade_limit(user)
    if economy.boosts_bought_this_week(db, user.id) >= weekly_cap:
        raise HTTPException(status_code=400, detail=f"Достигнут недельный лимит бустов ({weekly_cap})")

    price = economy.next_boost_price(db, user)
    if user.balance < price:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно средств: нужно {price} УЕ",
        )

    user.balance -= price
    db.add(models.BoostPurchase(user_id=user.id, price=price))
    db.add(
        models.Transaction(
            user_id=user.id,
            type="boost",
            amount=-price,
            note=f"Покупка буста (+1 сделка) за {price} УЕ (DEMO)",
        )
    )
    db.commit()
    db.refresh(user)
    return serialize_user(db, user)
