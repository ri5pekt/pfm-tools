#!/usr/bin/env python3
"""
One-time setup script to authorize Google Sheets API access using OAuth 2.0.

This script performs the initial OAuth authorization flow and saves the refresh token
for future use. After running this once, the application will automatically use the
saved token without requiring user interaction.

Usage:
    python -m app.scripts.setup_google_oauth
    # or
    python backend/app/scripts/setup_google_oauth.py
"""

import os
import sys
import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Scopes required for Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


def setup_oauth():
    """Perform one-time OAuth authorization and save token."""
    import os

    # Read directly from environment to avoid Settings validation issues
    credentials_path = os.getenv('GOOGLE_SHEETS_OAUTH_CREDENTIALS_PATH')
    if not credentials_path:
        print("ERROR: GOOGLE_SHEETS_OAUTH_CREDENTIALS_PATH not set in environment")
        print("Please set this to the path of your OAuth client credentials JSON file")
        print("Example: export GOOGLE_SHEETS_OAUTH_CREDENTIALS_PATH=backend/credentials/client_secret_google_sheets.json")
        return False

    if not os.path.exists(credentials_path):
        print(f"ERROR: Credentials file not found: {credentials_path}")
        print("Please download your OAuth client credentials from Google Cloud Console")
        return False

    # Determine token file path
    token_path = os.getenv('GOOGLE_SHEETS_OAUTH_TOKEN_PATH')
    if not token_path:
        # Default to same directory as credentials, with .token extension
        token_path = str(Path(credentials_path).parent / "google_sheets_token.pickle")
        print(f"Using default token path: {token_path}")

    creds = None

    # Check if we already have a valid token
    if os.path.exists(token_path):
        print(f"Loading existing token from: {token_path}")
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            print(f"Warning: Could not load existing token: {e}")
            creds = None

    # If no valid credentials, do OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Could not refresh token: {e}")
                creds = None

        if not creds:
            print("\n" + "="*60)
            print("Starting OAuth authorization flow...")
            print("A browser window will open for you to authorize access.")
            print("="*60 + "\n")

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                print("\n[SUCCESS] Authorization successful!")
            except Exception as e:
                print(f"\nERROR: Authorization failed: {e}")
                return False

        # Save credentials for future use
        print(f"Saving token to: {token_path}")
        try:
            os.makedirs(os.path.dirname(token_path) if os.path.dirname(token_path) else '.', exist_ok=True)
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
            print("[SUCCESS] Token saved successfully!")
        except Exception as e:
            print(f"ERROR: Could not save token: {e}")
            return False
    else:
        print("[INFO] Valid token already exists. No authorization needed.")

    print("\n" + "="*60)
    print("OAuth setup complete!")
    print(f"Token saved at: {token_path}")
    print("You can now use Google Sheets export in your application.")
    print("="*60)
    return True


if __name__ == '__main__':
    success = setup_oauth()
    sys.exit(0 if success else 1)

