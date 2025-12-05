import json
from pathlib import Path
from typing import Optional, Tuple

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

# ======================================================
# SERVICE ACCOUNT CONFIGURATION
# ======================================================

SERVICE_ACCOUNT_FILE = Path(__file__).parent.parent / "tools" / "service_account.json"

# Full permission required for:
# - Reading Google Docs from a shared folder
# - Exporting content as plain text
# - Creating / updating a policy doc
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Name of the folder in Drive shared with this service account
FOLDER_NAME = "Test_Documents"

# Local baseline policy text
LOCAL_TEMP_TXT = Path(__file__).parent.parent / "temp" / "data" / "temp.txt"


# ======================================================
# AUTH HELPER
# ======================================================

def get_drive_session() -> AuthorizedSession:
    """Create an AuthorizedSession using the service account JSON."""
    if not SERVICE_ACCOUNT_FILE.exists():
        raise FileNotFoundError(
            f"Service account JSON file missing at {SERVICE_ACCOUNT_FILE}"
        )

    creds = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=SCOPES,
    )
    print(f"[AUTH]: Using service account → {creds.service_account_email}")
    return AuthorizedSession(creds)


# ======================================================
# DRIVE HELPERS (AuthorizedSession-based)
# ======================================================

def find_shared_folder(session: AuthorizedSession) -> Optional[str]:
    """Find the shared folder ID for FOLDER_NAME."""
    query = (
        f"name = '{FOLDER_NAME}' and "
        "mimeType = 'application/vnd.google-apps.folder' and "
        "trashed = false"
    )

    try:
        resp = session.get(
            "https://www.googleapis.com/drive/v3/files",
            params={"q": query, "fields": "files(id, name)"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", [])
    except Exception as e:
        print("[ERROR]: Failed to list folders in Drive:", repr(e))
        return None

    if not files:
        print(f"[ERROR]: Shared folder '{FOLDER_NAME}' not found.")
        return None

    folder_id = files[0]["id"]
    print(f"[FOUND]: Shared folder '{FOLDER_NAME}' → ID {folder_id}")
    return folder_id


def _find_temp_docs_file(
    session: AuthorizedSession, folder_id: str
) -> Tuple[Optional[str], Optional[str]]:
    """Return (file_id, mimeType) for temp.docs inside the folder, or (None, None)."""
    query = (
        f"'{folder_id}' in parents and "
        "name = 'temp' and trashed = false"
    )

    resp = session.get(
        "https://www.googleapis.com/drive/v3/files",
        params={"q": query, "fields": "files(id, name, mimeType)"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    files = data.get("files", [])
    if not files:
        print("[INFO]: temp.docs not found inside shared folder.")
        return None, None

    file_id = files[0]["id"]
    mime_type = files[0].get("mimeType")
    print(f"[FOUND]: temp.docs → ID {file_id}, mimeType={mime_type}")
    return file_id, mime_type


# ======================================================
# FETCH temp.docs → SAVE AS temp.txt
# ======================================================

def fetch_temp_docs() -> None:
    """Download temp.docs from Drive and save it as local temp.txt."""
    try:
        session = get_drive_session()

        folder_id = find_shared_folder(session)
        if not folder_id:
            return

        file_id, mime_type = _find_temp_docs_file(session, folder_id)
        if not file_id:
            print("[WARN]: No temp.docs file to download. Skipping fetch.")
            return

        # If it's a Google Docs, use the export endpoint
        if mime_type == "application/vnd.google-apps.document":
            export_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
            params = {"mimeType": "text/plain"}
        else:
            # Fallback: treat it as a regular file
            export_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
            params = {"alt": "media"}

        resp = session.get(export_url, params=params, timeout=60)
        resp.raise_for_status()
        text_content = resp.text

        LOCAL_TEMP_TXT.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_TEMP_TXT.write_text(text_content, encoding="utf-8")
        print(f"[OK]: Downloaded temp.docs → {LOCAL_TEMP_TXT}")

    except Exception as e:
        print("[ERROR]: fetch_temp_docs() failed:", repr(e))


# ======================================================
# UPLOAD temp.txt → temp.docs
# ======================================================

def upload_and_replace_temp_docs() -> None:
    """Upload local temp.txt into Drive as temp.docs (create or replace)."""
    try:
        session = get_drive_session()

        folder_id = find_shared_folder(session)
        if not folder_id:
            return

        if not LOCAL_TEMP_TXT.exists():
            print("[ERROR]: Local temp.txt file not found. Upload aborted.")
            return

        file_id, mime_type = _find_temp_docs_file(session, folder_id)

        # Read the text we want to upload
        content = LOCAL_TEMP_TXT.read_text(encoding="utf-8")

        # If the file already exists, update its content via media upload
        if file_id:
            print(f"[UPLOAD]: Updating existing temp.docs (ID {file_id}) with new content.")
        else:
            # First create a new Google Docs file, then update its content
            print("[UPLOAD]: Creating new temp.docs in Drive.")
            metadata = {
                "name": "temp.docs",
                "mimeType": "application/vnd.google-apps.document",
                "parents": [folder_id],
            }
            meta_resp = session.post(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Content-Type": "application/json"},
                data=json.dumps(metadata),
                timeout=15,
            )
            meta_resp.raise_for_status()
            file_id = meta_resp.json()["id"]
            print(f"[OK]: Created temp.docs → ID {file_id}")

        # Now upload the plain-text content into the Docs file
        upload_url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}"
        upload_params = {"uploadType": "media"}

        upload_resp = session.patch(
            upload_url,
            params=upload_params,
            data=content.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=60,
        )
        upload_resp.raise_for_status()
        print("[OK]: Uploaded local temp.txt content to temp.docs.")

    except Exception as e:
        print("[ERROR]: upload_and_replace_temp_docs() failed:", repr(e))


if __name__ == "__main__":
    # Simple manual test helpers
    print("Testing fetch_temp_docs()...")
    fetch_temp_docs()
