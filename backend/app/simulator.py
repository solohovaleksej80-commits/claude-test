"""DEMO trade simulator.

Generates simulated trades on an interval. Unlike the original spec, this
HONESTLY produces both profitable AND losing outcomes — a real strategy cannot
guarantee profit, and a training tool must not pretend otherwise. Every trade
is flagged is_demo=True.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from .database import SessionLocal
from . import models
from .ws_manager import manager

ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ARB/USDT"]

# Daily counters (reset at 00:00 UTC).
_counters = {"analyzed": 0, "profitable": 0, "day": None}


def _reset_if_new_day() -> None:
    today = datetime.now(timezone.utc).date()
    if _counters["day"] != today:
        _counters["day"] = today
        _counters["analyzed"] = 0
        _counters["profitable"] = 0


def get_counters() -> dict:
    _reset_if_new_day()
    return {"analyzed": _counters["analyzed"], "profitable": _counters["profitable"]}


def _make_trade() -> dict:
    asset = random.choice(ASSETS)
    volume = round(random.uniform(100_000, 5_000_000), 2)
    # Honest distribution: ~62% winners, ~38% losers. Magnitude -2.5%..+2.5%.
    if random.random() < 0.62:
        slippage = round(random.uniform(0.3, 2.5), 3)
    else:
        slippage = round(random.uniform(-2.5, -0.3), 3)
    profit = round(volume * slippage / 100, 2)
    return {"asset": asset, "volume": volume, "slippage": slippage, "profit": profit}


def _analyze_seconds() -> int:
    hour = datetime.now(timezone.utc).hour
    return random.randint(10, 15)


def _interval_seconds() -> int:
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 6:  # night (UTC) — slower
        return random.randint(15, 30)
    return random.randint(5, 15)


async def _spawn_trade() -> None:
    _reset_if_new_day()
    data = _make_trade()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    analyze_secs = _analyze_seconds()

    db = SessionLocal()
    try:
        trade = models.Trade(
            asset=data["asset"],
            volume=data["volume"],
            slippage=data["slippage"],
            profit=data["profit"],
            state="analyzing",
            analyze_until=now + timedelta(seconds=analyze_secs),
            is_demo=True,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        trade_id = trade.id
    finally:
        db.close()

    _counters["analyzed"] += 1
    await manager.broadcast(
        {
            "type": "trade_new",
            "demo": True,
            "trade": {
                "id": trade_id,
                "asset": data["asset"],
                "volume": data["volume"],
                "state": "analyzing",
                "analyze_seconds": analyze_secs,
            },
            "counters": get_counters(),
        }
    )

    # Schedule the analysis -> open transition.
    asyncio.create_task(_finish_analysis(trade_id, analyze_secs))


async def _finish_analysis(trade_id: int, analyze_secs: int) -> None:
    await asyncio.sleep(analyze_secs)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    try:
        trade = db.get(models.Trade, trade_id)
        if not trade or trade.state != "analyzing":
            return
        trade.state = "open"
        trade.open_until = now + timedelta(minutes=15)
        db.commit()
        payload = {
            "id": trade.id,
            "asset": trade.asset,
            "volume": trade.volume,
            "slippage": trade.slippage,
            "profit": trade.profit,
            "state": "open",
            "open_seconds": 15 * 60,
        }
    finally:
        db.close()

    if payload["profit"] >= 0:
        _counters["profitable"] += 1

    await manager.broadcast(
        {"type": "trade_open", "demo": True, "trade": payload, "counters": get_counters()}
    )
    asyncio.create_task(_expire_trade(trade_id, 15 * 60))


async def _expire_trade(trade_id: int, open_secs: int) -> None:
    await asyncio.sleep(open_secs)
    db = SessionLocal()
    try:
        trade = db.get(models.Trade, trade_id)
        if not trade or trade.state != "open":
            return  # already accepted
        trade.state = "missed"
        db.commit()
    finally:
        db.close()
    await manager.broadcast({"type": "trade_missed", "demo": True, "trade_id": trade_id})


async def run_simulator(stop_event: asyncio.Event) -> None:
    """Main loop. Cancellable via stop_event."""
    while not stop_event.is_set():
        try:
            await _spawn_trade()
        except Exception as exc:  # keep the loop alive
            print(f"[simulator] error: {exc}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_interval_seconds())
        except asyncio.TimeoutError:
            pass
