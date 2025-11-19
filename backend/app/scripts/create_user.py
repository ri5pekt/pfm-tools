# backend/app/scripts/create_user.py
import argparse
from getpass import getpass

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.auth.models import User
from app.core.security import get_password_hash


def create_user(email: str, password: str, is_admin: bool = False) -> None:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"⚠️ User with email {email} already exists (id={existing.id})")
            return

        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_admin=is_admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        role = "admin" if is_admin else "regular"
        print(f"✅ Created {role} user id={user.id}, email={user.email}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Create a PFM Tools user")
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", help="User password (optional, will prompt)")
    parser.add_argument("--admin", action="store_true", help="Create as admin")

    args = parser.parse_args()

    password = args.password or getpass("Password: ")

    if not password:
        raise SystemExit("Password cannot be empty")

    create_user(args.email, password, args.admin)


if __name__ == "__main__":
    main()
