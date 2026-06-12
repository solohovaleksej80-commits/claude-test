import asyncio
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import economy, models, simulator
from ..auth import authenticate
from ..database import SessionLocal, get_db
from ..schemas import AcceptResult, CountersOut, TradeOut, TransactionOut
from ..ws_manager import manager

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/counters", response_model=CountersOut)
def counters():
    return simulator.get_counters()


@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    state: str | None = Query(default=None),
    limit: int = Query(default=40, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(models.Trade)
    if state:
        q = q.filter(models.Trade.state == state)
    rows = q.order_by(models.Trade.id.desc()).offset(offset).limit(limit).all()
    return rows


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    type: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: models.User = Depends(authenticate),
    db: Session = Depends(get_db),
):
    q = db.query(models.Transaction).filter(models.Transaction.user_id == user.id)
    if type:
        q = q.filter(models.Transaction.type == type)
    return q.order_by(models.Transaction.id.desc()).offset(offset).limit(limit).all()


async def _complete_trade(user_id: int, trade_id: int, user_trade_id: int, delay: float):
    """After a short 'execution', realize the (possibly negative) DEMO profit."""
    await asyncio.sleep(delay)
    db = SessionLocal()
    try:
        trade = db.get(models.Trade, trade_id)
        user = db.get(models.User, user_id)
        ut = db.get(models.UserTrade, user_trade_id)
        if not (trade and user and ut):
            return
        profit = trade.profit
        trade.state = "completed"
        ut.realized_profit = profit
        user.balance += profit
        user.total_trades += 1
        user.level = economy.level_for(user.total_trades)["name"]
        db.add(
            models.Transaction(
                user_id=user.id,
                type="trade_profit",
                amount=profit,
                note=f"DEMO сделка #{trade.id} {trade.asset} ({'+' if profit >= 0 else ''}{profit} УЕ)",
            )
        )
        db.commit()
        balance = user.balance
    finally:
        db.close()
    await manager.broadcast(
        {
            "type": "trade_completed",
            "demo": True,
            "trade_id": trade_id,
            "profit": profit,
            "user_id": user_id,
            "balance": round(balance, 2),
        }
    )


@router.post("/trades/{trade_id}/accept", response_model=AcceptResult)
async def accept_trade(
    trade_id: int,
    latency_ms: int | None = None,
    user: models.User = Depends(authenticate),
    db: Session = Depends(get_db),
):
    if user.tier < 2:
        return AcceptResult(ok=False, detail="Принятие сделок доступно с Этапа 2")

    trade = db.get(models.Trade, trade_id)
    if not trade:
        return AcceptResult(ok=False, detail="Сделка не найдена")
    if trade.state != "open":
        return AcceptResult(ok=False, detail="Сделка недоступна для принятия")

    if economy.remaining_trades_today(db, user) <= 0:
        price = economy.next_boost_price(db, user)
        return AcceptResult(
            ok=False,
            detail=f"Лимит сделок исчерпан. Купите буст за {price} УЕ (POST /api/boosts/buy)",
        )

    trade.state = "accepted"
    ut = models.UserTrade(
        user_id=user.id,
        trade_id=trade.id,
        accept_latency_ms=latency_ms,
    )
    db.add(ut)
    db.commit()
    db.refresh(ut)
    db.refresh(trade)

    delay = random.uniform(3, 30)
    asyncio.create_task(_complete_trade(user.id, trade.id, ut.id, delay))
    await manager.broadcast({"type": "trade_accepted", "demo": True, "trade_id": trade.id})

    return AcceptResult(
        ok=True,
        detail="Сделка принята (DEMO). Идёт исполнение.",
        trade=TradeOut.model_validate(trade, from_attributes=True),
        balance=round(user.balance, 2),
    )
