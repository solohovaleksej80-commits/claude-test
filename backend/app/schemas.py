from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    telegram_id: int
    username: str | None
    balance: float
    tier: int
    tier_name: str
    tier_expires_at: datetime | None
    total_trades: int
    level: str
    remaining_trades_today: int
    daily_limit: int
    next_boost_price: float
    referral_earnings: float
    sound_enabled: bool
    auto_turbo: bool
    next_level: str | None
    next_level_at: int | None
    currency: str = "УЕ (виртуальные, DEMO)"


class TradeOut(BaseModel):
    id: int
    asset: str
    volume: float
    slippage: float
    profit: float
    state: str
    is_demo: bool
    created_at: datetime


class TransactionOut(BaseModel):
    id: int
    type: str
    amount: float
    note: str | None
    created_at: datetime


class AcceptResult(BaseModel):
    ok: bool
    detail: str
    trade: TradeOut | None = None
    balance: float | None = None


class SettingsIn(BaseModel):
    sound_enabled: bool | None = None
    auto_turbo: bool | None = None


class CountersOut(BaseModel):
    analyzed: int
    profitable: int
