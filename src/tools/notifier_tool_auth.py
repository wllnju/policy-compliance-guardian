import os
import base64, shutil
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()

# ======================================================
# CONFIGURATION
# ======================================================

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

BASE_DIR = Path(__file__).resolve().parent

CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "notifier_token.json"

# SENDER_EMAIL = "hrfprofessional@gmail.com"
SENDER_EMAIL = "lwangucr@gmail.com"


# ======================================================
# AUTHENTICATION (fail-soft)
# ======================================================

def get_gmail_service():
    """
    Return a Gmail service client, or None if authentication fails.

    This is intentionally fail-soft so that network / OAuth issues
    do not crash the main workflow.
    """
    creds = None

    # Try loading existing token
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            print(f"[Notifier] Failed to load token file (will re-auth): {e}")
            creds = None

    # If no valid creds, either refresh or run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing Gmail OAuth token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[Notifier] Token refresh failed (skipping Gmail): {e}")
                return None
        else:
            # Interactive browser login; may fail behind VPN / firewall
            print("Opening Gmail OAuth browser login...")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE),
                    SCOPES,
                )
                creds = flow.run_local_server(
                    port=0,
                    open_browser=True,
                    authorization_prompt_message="",
                    success_message=(
                        "Gmail authentication successful. "
                        "You may close this window."
                    ),
                )
            except Exception as e:
                print(f"[Notifier] OAuth login failed (skipping Gmail): {e}")
                return None

        # Persist token (best-effort)
        try:
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
        except Exception as e:
            print(f"[Notifier] Failed to persist token (non-fatal): {e}")

    # Build Gmail service
    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"[Notifier] Failed to build Gmail service (skipping Gmail): {e}")
        return None


# ======================================================
# SEND EMAIL
# ======================================================
SMTP_USER = os.getenv("SMTP_USER")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def build_email_smtp(to_email: str, subject: str, body: str):
    """Create a MIME email for SMTP sending."""
    msg = MIMEMultipart()
    msg["To"] = to_email
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg

# ======================================================
# DELETE FOLDERS
# ======================================================

def delete_snapshot_folders():
    DEFAULT_USER_EMAIL = os.getenv("USER_EMAIL")

    TEMP_DIR_MONITORED = (
        Path(__file__).parent.parent
        / "temp"
        / "data"
        / "monitored_snapshots"
        / f"{DEFAULT_USER_EMAIL}_monitored_file"
    )
    TEMP_DIR_AUTHORIZED = (
        Path(__file__).parent.parent
        / "temp"
        / "data"
        / "authorized_snapshots"
        / f"{DEFAULT_USER_EMAIL}_authorized_file"
    )

    TEMP_DIR_DOCS_TOKEN = Path(__file__).parent.parent / "docs_fetcher_token.json"
    TEMP_DIR_NOTIFIER_TOKEN = Path(__file__).parent.parent / "notifier_token.json"

    # Delete monitored_snapshots folder
    if TEMP_DIR_MONITORED.exists() and TEMP_DIR_MONITORED.is_dir():
        shutil.rmtree(TEMP_DIR_MONITORED)
        print(f"Deleted folder: {TEMP_DIR_MONITORED}")
    else:
        print(f"Folder not found (skip): {TEMP_DIR_MONITORED}")

    # Delete authorized_snapshots folder
    if TEMP_DIR_AUTHORIZED.exists() and TEMP_DIR_AUTHORIZED.is_dir():
        shutil.rmtree(TEMP_DIR_AUTHORIZED)
        print(f"Deleted folder: {TEMP_DIR_AUTHORIZED}")
    else:
        print(f"Folder not found (skip): {TEMP_DIR_AUTHORIZED}")


# ======================================================
# UPLOAD AND REPLACE temp.docs IN GOOGLE DRIVE
# ======================================================

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
def upload_and_replace_temp_docs():
    """
    Upload local temp.txt to Google Drive and replace (or create) 'temp.docs'
    inside the 'Test_Documents' folder, using a service account and
    AuthorizedSession instead of googleapiclient/httplib2.
    """
    print("Uploading new temp.txt to Google Drive and replacing temp.docs ...")

    SERVICE_ACCOUNT_FILE = (
        Path(__file__).parent.parent / "tools" / "service_account.json"
    )
    SCOPES = ["https://www.googleapis.com/auth/drive"]
    FOLDER_NAME = "Test_Documents"

    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"Service account file missing at: {SERVICE_ACCOUNT_FILE}")
        return

    # Load service account credentials
    try:
        creds = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_FILE),
            scopes=SCOPES,
        )
    except Exception as e:
        print("[ERROR]: Failed to load service account credentials:", e)
        return

    print(f"[AUTH]: Using service account: {creds.service_account_email}")

    # Authorized HTTP session (uses requests under the hood)
    try:
        session = AuthorizedSession(creds)
    except Exception as e:
        print("[ERROR]: Failed to create AuthorizedSession:", e)
        return

    BASE_URL = "https://www.googleapis.com/drive/v3"
    UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

    # --------------------------------------------------
    # 1) Find target folder by name
    # --------------------------------------------------
    try:
        query = (
            f"name = '{FOLDER_NAME}' and "
            f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id, name)",
            "spaces": "drive",
        }
        resp = session.get(f"{BASE_URL}/files", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        folders = data.get("files", [])
    except Exception as e:
        print("[ERROR]: Failed to query folder from Drive:", e)
        return

    if not folders:
        print(f"[ERROR]: Folder '{FOLDER_NAME}' not shared with service account.")
        return

    folder_id = folders[0]["id"]
    print(f"[OK]: Found folder '{FOLDER_NAME}' → ID = {folder_id}")

    # --------------------------------------------------
    # 2) Find existing 'temp.docs' in that folder
    # --------------------------------------------------
    try:
        query = (
            f"'{folder_id}' in parents and "
            f"name = 'temp.docs' and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id, name)",
            "spaces": "drive",
        }
        resp = session.get(f"{BASE_URL}/files", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", [])
    except Exception as e:
        print("[ERROR]: Failed to query temp.docs from Drive:", e)
        return

    if not files:
        print("[INFO]: temp.docs not found. Will create a new one.")
        temp_docs_id = None
    else:
        temp_docs_id = files[0]["id"]
        print(f"[FOUND]: temp.docs → {temp_docs_id}")

    # --------------------------------------------------
    # 3) Read local temp.txt
    # --------------------------------------------------
    LOCAL_TEMP = Path(__file__).parent.parent / "temp" / "data" / "temp.txt"

    if not LOCAL_TEMP.exists():
        print("[ERROR]: temp.txt missing. Cannot upload.")
        return

    try:
        file_bytes = LOCAL_TEMP.read_bytes()
    except Exception as e:
        print("[ERROR]: Failed to read local temp.txt:", e)
        return

    # --------------------------------------------------
    # 4) If no temp.docs → create metadata first
    # --------------------------------------------------
    if not temp_docs_id:
        try:
            meta = {
                "name": "temp.docs",
                "parents": [folder_id],
            }
            resp = session.post(
                f"{BASE_URL}/files",
                json=meta,
                params={"fields": "id"},
                timeout=20,
            )
            resp.raise_for_status()
            temp_docs_id = resp.json()["id"]
            print(f"[OK]: temp.docs created → {temp_docs_id}")
        except Exception as e:
            print("[ERROR]: Failed to create temp.docs metadata:", e)
            return

    # --------------------------------------------------
    # 5) Upload new content via media upload
    # --------------------------------------------------
    try:
        resp = session.patch(
            f"{UPLOAD_URL}/{temp_docs_id}",
            params={"uploadType": "media"},
            data=file_bytes,
            headers={"Content-Type": "text/plain"},
            timeout=60,
        )
        resp.raise_for_status()
        print("[OK]: temp.docs content updated successfully.")
    except Exception as e:
        print("Failed to upload/replace temp.docs:", e)


def send_email(to_email: str, subject: str, body: str):
    """
    Send an email via SMTP (Gmail + app password), then clean up snapshot
    folders and update temp.docs in Drive.

    Any errors are logged but NOT raised, so callers won't crash.
    """
    # 1) Send email via SMTP (best effort)
    if not SMTP_USER or not SMTP_APP_PASSWORD:
        print("[Notifier] SMTP_USER/SMTP_APP_PASSWORD not set; skipping email send.")
    else:
        try:
            msg = build_email_smtp(to_email, subject, body)
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                server.login(SMTP_USER, SMTP_APP_PASSWORD)
                server.send_message(msg)
            print(f"[Notifier] Email sent to {to_email} via SMTP.")
        except Exception as e:
            print(f"[Notifier] SMTP send failed (non-fatal): {e}")

    # 2) Snapshot cleanup (best effort)
    try:
        delete_snapshot_folders()
    except Exception as e:
        print(f"[Notifier] Failed to delete snapshot folders (non-fatal): {e}")

    ENABLE_DRIVE_SYNC = os.getenv("ENABLE_DRIVE_SYNC", "false").lower() == "true"
    if ENABLE_DRIVE_SYNC:
        # 3) Upload new temp.txt → replace temp.docs in Drive (best effort)
        try:
            upload_and_replace_temp_docs()
        except Exception as e:
            print(f"[Notifier] Failed to upload/replace temp.docs (non-fatal): {e}")
    else:
        print("ENABLE_DRIVE_SYNC is ", ENABLE_DRIVE_SYNC)