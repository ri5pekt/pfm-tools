# Google Sheets Export Setup Guide

This guide explains how to set up Google Sheets export using OAuth 2.0 authentication.

## File Locations

### 1. OAuth Credentials File
**Location:** `backend/credentials/client_secret_google_sheets.json` (or any path you prefer)

This is the JSON file you downloaded from Google Cloud Console when creating the OAuth client ID.

**Example path:** `/path/to/your/credentials.json`

### 2. OAuth Token File (created automatically)
**Location:** `backend/google_sheets_token.pickle` (default, or custom path)

This file is created automatically when you run the setup script. It contains your refresh token for automatic authentication.

## Setup Steps

### Step 1: Place Credentials File
Copy your downloaded OAuth credentials JSON file to the backend directory:
```bash
# Example: Save it as backend/credentials/client_secret_google_sheets.json
cp ~/Downloads/your-oauth-credentials.json backend/credentials/client_secret_google_sheets.json
```

**Note:** The file is already placed at `backend/credentials/client_secret_google_sheets.json`

### Step 2: Configure Environment Variables
Add these to your `.env` file:

```env
# OAuth 2.0 Configuration (for organization projects)
GOOGLE_SHEETS_OAUTH_CREDENTIALS_PATH=backend/credentials/client_secret_google_sheets.json
GOOGLE_SHEETS_OAUTH_TOKEN_PATH=backend/credentials/google_sheets_token.pickle
GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id-here
GOOGLE_SHEETS_SHEET_NAME=Ulta Exports
```

**Note:**
- If you don't set `GOOGLE_SHEETS_OAUTH_TOKEN_PATH`, it will default to `google_sheets_token.pickle` in the same directory as the credentials file (i.e., `backend/credentials/google_sheets_token.pickle`)
- Use relative paths from project root, or absolute paths if preferred

### Step 3: Run One-Time Setup Script
This script will open a browser for you to authorize access, then save the token for future use:

```bash
# From the backend directory
python -m app.scripts.setup_google_oauth

# Or from project root
python backend/app/scripts/setup_google_oauth.py
```

**What happens:**
1. A browser window will open
2. Sign in with your Google account
3. Grant permissions to the app
4. The script saves a refresh token to `google_sheets_token.pickle`
5. Future exports will use this token automatically (no user interaction needed)

### Step 4: Share Your Google Sheet
Make sure the Google account you authorized has access to the spreadsheet:
- Open your Google Sheet
- Click "Share"
- Ensure your Google account has "Editor" permissions

### Step 5: Test the Export
Run a manual export from the Ulta Marketplace view. The export should now:
- Save to CSV (as before)
- Also export to Google Sheets automatically

## Alternative: Service Account (if allowed by your org)

If your organization allows service account keys, you can use service account authentication instead:

```env
# Service Account Configuration
GOOGLE_SHEETS_SERVICE_ACCOUNT_PATH=/path/to/service-account-key.json
GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id-here
GOOGLE_SHEETS_SHEET_NAME=Ulta Exports
```

Then share your Google Sheet with the service account email address.

## Troubleshooting

### "No valid Google credentials found"
- Make sure you've run the setup script (`setup_google_oauth.py`)
- Check that the token file exists at the path specified in `GOOGLE_SHEETS_OAUTH_TOKEN_PATH`
- Verify the credentials file path is correct

### "Failed to open spreadsheet"
- Make sure your Google account has access to the spreadsheet
- Check that the spreadsheet ID is correct (from the URL: `/d/SPREADSHEET_ID/edit`)

### Token expired
- The script automatically refreshes expired tokens
- If refresh fails, run the setup script again to re-authorize

## Security Notes

- Keep `credentials.json` and `google_sheets_token.pickle` secure
- Don't commit these files to version control
- Add them to `.gitignore`:
  ```
  credentials.json
  google_sheets_token.pickle
  *.pickle
  ```

