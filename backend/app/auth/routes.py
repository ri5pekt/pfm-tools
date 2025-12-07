# backend/app/auth/routes.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core import security
from app.auth import models, schemas
from app.dependencies import get_current_active_user

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


@router.post("/login", response_model=schemas.Token)
async def login(
    payload: schemas.LoginRequest,
    db: Session = Depends(get_db),
):
    import logging
    logger = logging.getLogger(__name__)

    # Try case-insensitive email match
    user = (
        db.query(models.User)
        .filter(models.User.email.ilike(payload.email))
        .first()
    )

    if not user:
        logger.warning(f"Login attempt with non-existent email: '{payload.email}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Verify password
    password_valid = security.verify_password(payload.password, user.hashed_password)

    if not password_valid:
        logger.warning(f"Login attempt with incorrect password for email: '{payload.email}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = security.create_access_token(
        {
            "user_id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=schemas.UserMe)
async def read_me(current_user=Depends(get_current_active_user)):
    return current_user
