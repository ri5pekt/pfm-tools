# backend/app/scripts/reset_password.py
import argparse
from getpass import getpass

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.auth.models import User
from app.core.security import get_password_hash


def reset_password(email: str, password: str) -> None:
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User with email {email} not found")
            return

        user.hashed_password = get_password_hash(password)
        db.commit()
        db.refresh(user)
        print(f"✅ Password reset for user id={user.id}, email={user.email}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Reset a user's password")
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", help="New password (optional, will prompt)")

    args = parser.parse_args()

    password = args.password or getpass("New password: ")

    if not password:
        raise SystemExit("Password cannot be empty")

    reset_password(args.email, password)


if __name__ == "__main__":
    main()

