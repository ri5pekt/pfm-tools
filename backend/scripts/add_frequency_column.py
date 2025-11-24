"""
Script to add the frequency column to the scheduled_exports table.
Run this script to update existing database schema.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.db import engine, SessionLocal

def add_frequency_column():
    """Add frequency column to scheduled_exports table if it doesn't exist."""
    db = SessionLocal()
    try:
        # Check if column exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='scheduled_exports' AND column_name='frequency'
        """))

        if result.fetchone():
            print("✓ Column 'frequency' already exists in scheduled_exports table")
        else:
            # Add the column
            db.execute(text("""
                ALTER TABLE scheduled_exports
                ADD COLUMN frequency INTEGER DEFAULT 1 NOT NULL
            """))
            db.commit()
            print("✓ Successfully added 'frequency' column to scheduled_exports table")

    except Exception as e:
        db.rollback()
        print(f"✗ Error adding frequency column: {e}")
        print("\nIf the table doesn't exist yet, restart your backend server and it will be created automatically.")
        return False
    finally:
        db.close()

    return True

if __name__ == "__main__":
    print("Adding frequency column to scheduled_exports table...")
    add_frequency_column()

