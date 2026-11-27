"""Limit file access to the CRM and price shared with a service account.
No Gmail access granted by service account, no external sending.
"""
import io
import os
import json
import imaplib
import ssl
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from smtp_preflight import validate_sender

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive.readonly"]

def file_services():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    expected_service = os.environ.get("EXPECTED_SERVICE_ACCOUNT", "").strip().lower()
    if expected_service and info.get("client_email", "").lower() != expected_service:
        raise ValueError("Service account identity mismatch")
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    print("SERVICE_ACCOUNT_CONFIG_OK", flush=True)
    return (build("sheets", "v4", credentials=creds, cache_discovery=False),
            build("drive", "v3", credentials=creds, cache_discovery=False))

def verify_crm(sheets, sid, expected):
    print("STAGE CRM_READ", flush=True)
    values = sheets.spreadsheets().values().get(spreadsheetId=sid,
        range="'Налаштування'!A2:B30").execute().get("values", [])
    settings = {r[0]: r[1] for r in values if len(r) >= 2}
    if settings.get("Основна пошта", "").strip().lower() != expected.strip().lower():
        raise ValueError("CRM identity mismatch")
    if not settings.get("Прайс Drive ID"):
        raise ValueError("Price ID missing in CRM")
    print("CRM_READ_OK", flush=True)
    return settings

def load_price(drive, file_id):
    print("STAGE PDF_METADATA", flush=True)
    metadata = drive.files().get(fileId=file_id, fields="name,mimeType,size,trashed").execute()
    if (metadata.get("trashed") or metadata.get("mimeType") != "application/pdf"
        or int(metadata.get("size", "0")) != 556589):
        raise ValueError("Price metadata mismatch; review price configuration")
    print("STAGE PDF_DOWNLOAD", flush=True)
    stream = io.BytesIO()
    downloader = MediaIoBaseDownload(stream, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    content = stream.getvalue()
    if len(content) != 556589 or not content.startswith(b"%PDF-"):
        raise ValueError("Price content mismatch")
    print("PRICE_PDF_OK", flush=True)
    return content

def imap_preflight():
    address = validate_sender(os.environ["EMAIL_ADDRESS"], os.environ["EXPECTED_GMAIL"])
    with imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context(), timeout=30) as conn:
        conn.login(address, os.environ["EMAIL_APP_PASSWORD"])
        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("IMAP read-only inbox unavailable")
    print("IMAP_READ_ONLY_OK")

def safe_http_error(exc):
    """Log only numeric status and recognized error categories, not raw messages or URLs."""
    status = getattr(exc.resp, "status", None)
    reasons = set()
    try:
        error = json.loads(exc.content).get("error", {})
        for item in error.get("errors", []) + error.get("details", []):
            reason = item.get("reason", "")
            if reason in {"accessNotConfigured", "SERVICE_DISABLED", "PERMISSION_DENIED",
                          "forbidden", "insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
                          "notFound", "NOT_FOUND", "badRequest", "invalid", "rateLimitExceeded",
                          "userRateLimitExceeded", "RESOURCE_EXHAUSTED", "UNAUTHENTICATED",
                          "unauthorized", "insufficientFilePermissions", "dailyLimitExceeded"}:
                reasons.add(reason)
        reason = error.get("status", "")
        if reason in {"PERMISSION_DENIED", "NOT_FOUND", "UNAUTHENTICATED", "INVALID_ARGUMENT", "RESOURCE_EXHAUSTED"}:
            reasons.add(reason)
    except (ValueError, TypeError, AttributeError):
        pass
    return f"HTTP {status}; reason={','.join(sorted(reasons)) or 'UNCLASSIFIED'}"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["files-check", "imap-check"], required=True)
    mode = parser.parse_args().mode
    try:
        if mode == "imap-check":
            imap_preflight()
        else:
            sheets, drive = file_services()
            settings = verify_crm(sheets, os.environ["CRM_ID"], os.environ["EXPECTED_GMAIL"])
            print("CRM_READ_OK")
            load_price(drive, settings["Прайс Drive ID"])
            print("PRICE_PDF_OK")
    except Exception as exc:
        print("CHECK_ERROR", mode, safe_http_error(exc) if isinstance(exc, HttpError) else type(exc).__name__)
        raise SystemExit(1)
