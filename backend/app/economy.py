"""Virtual economy rules: tiers, boosts, levels, referrals.

All amounts are in учебные единицы (УЕ) — virtual units, NOT real money.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

# Tier configuration. Price in УЕ/month, daily trade limit.
TIERS = {
    1: {"name": "Информационный", "price": 10, "daily_limit": 0},
    2: {"name": "Ручные сделки", "price": 50, "daily_limit": 5},
    3: {"name": "Автоторговля", "price": 150, "daily_limit": 20},
}

# Boost prices for the Nth boost bought today (1-indexed). After the 6th: previous * 2.
BASE_BOOST_PRICES = [5, 10, 20, 40, 80, 160]

# Levels: required total trades -> bonuses.
LEVELS = [
    {"name": "bronze", "trades": 0, "bonus_trades": 0, "boost_discount": 0.0},
    {"name": "silver", "trades": 100, "bonus_trades": 1, "boost_discount": 0.0},
    {"name": "gold", "trades": 500, "bonus_trades": 3, "boost_discount": 0.05},
    {"name": "platinum", "trades": 1000, "bonus_trades": 5, "boost_discount": 0.10},
]

REFERRAL_RATE = 0.15  # 15% of referred user's first subscription


def utc_day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def level_for(total_trades: int) -> dict:
    current = LEVELS[0]
    for lvl in LEVELS:
        if total_trades >= lvl["trades"]:
            current = lvl
    return current


def next_level(total_trades: int) -> dict | None:
    for lvl in LEVELS:
        if total_trades < lvl["trades"]:
            return lvl
    return None


def daily_trade_limit(user: models.User) -> int:
    """Base tier limit + level bonus + boosts bought today."""
    base = TIERS[user.tier]["daily_limit"]
    bonus = level_for(user.total_trades)["bonus_trades"]
    return base + bonus


def boosts_bought_today(db: Session, user_id: int) -> int:
    return (
        db.query(func.count(models.BoostPurchase.id))
        .filter(
            models.BoostPurchase.user_id == user_id,
            models.BoostPurchase.created_at >= utc_day_start(),
        )
        .scalar()
        or 0
    )


def boosts_bought_this_week(db: Session, user_id: int) -> int:
    week_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    return (
        db.query(func.count(models.BoostPurchase.id))
        .filter(
            models.BoostPurchase.user_id == user_id,
            models.BoostPurchase.created_at >= week_ago,
        )
        .scalar()
        or 0
    )


def next_boost_price(db: Session, user: models.User) -> float:
    n = boosts_bought_today(db, user.id)  # already bought today
    idx = n  # price for the (n+1)th boost -> 0-indexed n
    if idx < len(BASE_BOOST_PRICES):
        price = BASE_BOOST_PRICES[idx]
    else:
        price = BASE_BOOST_PRICES[-1] * (2 ** (idx - len(BASE_BOOST_PRICES) + 1))
    discount = level_for(user.total_trades)["boost_discount"]
    return round(price * (1 - discount), 2)


def trades_accepted_today(db: Session, user_id: int) -> int:
    return (
        db.query(func.count(models.UserTrade.id))
        .filter(
            models.UserTrade.user_id == user_id,
            models.UserTrade.accepted_at >= utc_day_start(),
        )
        .scalar()
        or 0
    )


def remaining_trades_today(db: Session, user: models.User) -> int:
    used = trades_accepted_today(db, user.id)
    return max(0, daily_trade_limit(user) + boosts_bought_today(db, user.id) - used)
