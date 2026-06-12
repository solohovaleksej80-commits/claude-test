"""Telegram Web App initData validation.

In DEV_MODE the validation is bypassed so the Mini App can be opened in a
plain browser. In production set DEV_MODE=false and a real BOT_TOKEN.
"""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import get_db


def _verify_init_data(init_data: str) -> dict:
    """Validate Telegram Web App initData signature, return parsed user dict."""
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="missing hash")

    check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        raise HTTPException(status_code=401, detail="invalid initData signature")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="no user in initData")
    return json.loads(user_raw)


def _get_or_create_user(db: Session, tg_user: dict, ref: str | None = None) -> models.User:
    telegram_id = int(tg_user["id"])
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        return user

    referred_by = None
    if ref and ref.startswith("ref_"):
        candidate = ref[4:]
        if candidate.isdigit() and int(candidate) != telegram_id:
            referred_by = int(candidate)

    user = models.User(
        telegram_id=telegram_id,
        username=tg_user.get("username"),
        balance=settings.start_balance,
        referred_by=referred_by,
    )
    db.add(user)
    db.flush()
    db.add(
        models.Transaction(
            user_id=user.id,
            type="deposit_demo",
            amount=settings.start_balance,
            note="Стартовый виртуальный баланс (DEMO)",
        )
    )
    db.commit()
    db.refresh(user)
    return user


def authenticate(
    db: Session = Depends(get_db),
    x_init_data: str | None = Header(default=None),
    x_dev_user_id: str | None = Header(default=None),
) -> models.User:
    """FastAPI dependency: resolve the current user from initData (or dev header)."""
    if settings.dev_mode:
        tg_id = int(x_dev_user_id) if x_dev_user_id and x_dev_user_id.isdigit() else 100001
        return _get_or_create_user(db, {"id": tg_id, "username": f"dev_{tg_id}"})

    if not x_init_data:
        raise HTTPException(status_code=401, detail="missing X-Init-Data header")
    tg_user = _verify_init_data(x_init_data)
    return _get_or_create_user(db, tg_user)
