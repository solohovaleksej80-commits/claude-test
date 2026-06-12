from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..auth import authenticate
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api", tags=["referrals"])


@router.get("/referral")
def referral_info(user: models.User = Depends(authenticate), db: Session = Depends(get_db)):
    invited = (
        db.query(models.User).filter(models.User.referred_by == user.telegram_id).count()
    )
    history = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user.id,
            models.Transaction.type == "referral_bonus",
        )
        .order_by(models.Transaction.id.desc())
        .limit(50)
        .all()
    )
    return {
        "link": f"https://t.me/your_bot?start=ref_{user.telegram_id}",
        "invited_count": invited,
        "earnings": round(user.referral_earnings, 2),
        "history": [
            {"amount": h.amount, "note": h.note, "created_at": h.created_at} for h in history
        ],
    }
