# backend/app/auth/schemas.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int
    email: EmailStr
    is_admin: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserBase(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)


class UserMe(UserBase):
    created_at: Optional[datetime] | None = None
