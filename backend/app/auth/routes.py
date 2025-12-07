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

    # Debug logging
    logger.info(f"Login attempt - Email: '{payload.email}' (len={len(payload.email)}), Password len: {len(payload.password)}")

    # Try case-insensitive email match
    user = (
        db.query(models.User)
        .filter(models.User.email.ilike(payload.email))
        .first()
    )

    if not user:
        logger.warning(f"Login attempt with non-existent email: '{payload.email}'")
        # Log all users for debugging
        all_users = db.query(models.User).all()
        logger.warning(f"Available users: {[u.email for u in all_users]}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    logger.info(f"User found: id={user.id}, email='{user.email}', active={user.is_active}")

    # Verify password
    password_valid = security.verify_password(payload.password, user.hashed_password)
    logger.info(f"Password verification result: {password_valid}")

    if not password_valid:
        logger.warning(f"Login attempt with incorrect password for email: '{payload.email}'")
        logger.warning(f"Password verification failed for user id={user.id}, email='{user.email}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    logger.info(f"Login successful for user id={user.id}, email='{user.email}'")

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
