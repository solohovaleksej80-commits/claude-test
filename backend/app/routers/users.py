from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..auth import authenticate
from ..database import get_db
from ..schemas import SettingsIn, UserOut
from .common import serialize_user

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(user: models.User = Depends(authenticate), db: Session = Depends(get_db)):
    return serialize_user(db, user)


@router.post("/settings", response_model=UserOut)
def update_settings(
    payload: SettingsIn,
    user: models.User = Depends(authenticate),
    db: Session = Depends(get_db),
):
    if payload.sound_enabled is not None:
        user.sound_enabled = payload.sound_enabled
    if payload.auto_turbo is not None:
        user.auto_turbo = payload.auto_turbo
    db.commit()
    db.refresh(user)
    return serialize_user(db, user)
