from sqlalchemy.orm import Session

from .. import economy, models


def serialize_user(db: Session, user: models.User) -> dict:
    nxt = economy.next_level(user.total_trades)
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "balance": round(user.balance, 2),
        "tier": user.tier,
        "tier_name": economy.TIERS[user.tier]["name"],
        "tier_expires_at": user.tier_expires_at,
        "total_trades": user.total_trades,
        "level": economy.level_for(user.total_trades)["name"],
        "remaining_trades_today": economy.remaining_trades_today(db, user),
        "daily_limit": economy.daily_trade_limit(user),
        "next_boost_price": economy.next_boost_price(db, user),
        "referral_earnings": round(user.referral_earnings, 2),
        "sound_enabled": user.sound_enabled,
        "auto_turbo": user.auto_turbo,
        "next_level": nxt["name"] if nxt else None,
        "next_level_at": nxt["trades"] if nxt else None,
    }
