from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Virtual economy — учебные единицы (УЕ), не реальные деньги.
    balance: Mapped[float] = mapped_column(Float, default=0.0)

    tier: Mapped[int] = mapped_column(Integer, default=1)  # 1=info, 2=manual, 3=auto
    tier_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    total_trades: Mapped[int] = mapped_column(Integer, default=0)  # accepted/executed trades
    level: Mapped[str] = mapped_column(String(16), default="bronze")

    referred_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # telegram_id
    referral_earnings: Mapped[float] = mapped_column(Float, default=0.0)

    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_turbo: Mapped[bool] = mapped_column(Boolean, default=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")


class Trade(Base):
    """A simulated DEMO trade. Results include both profits and losses."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset: Mapped[str] = mapped_column(String(16))
    volume: Mapped[float] = mapped_column(Float)
    slippage: Mapped[float] = mapped_column(Float)  # percent, may be negative
    profit: Mapped[float] = mapped_column(Float)  # volume * slippage / 100, may be negative
    state: Mapped[str] = mapped_column(String(16), default="analyzing", index=True)
    # analyzing -> open -> accepted -> executing -> completed | missed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    analyze_until: Mapped[datetime] = mapped_column(DateTime)
    open_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class UserTrade(Base):
    """Links a user to a trade they accepted."""

    __tablename__ = "user_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"), index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    accept_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realized_profit: Mapped[float | None] = mapped_column(Float, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # type: deposit_demo, subscription, boost, turbo, trade_profit, referral_bonus, withdraw_demo, admin_adjust
    type: Mapped[str] = mapped_column(String(24), index=True)
    amount: Mapped[float] = mapped_column(Float)  # signed, in УЕ
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="transactions")


class BoostPurchase(Base):
    __tablename__ = "boost_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
