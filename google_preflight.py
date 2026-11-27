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
from smtp_preflight import validate_sender

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive.readonly"]

def file_services():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=SCOPES)
    return (build("sheets", "v4", credentials=creds, cache_discovery=False),
            build("drive", "v3", credentials=creds, cache_discovery=False))

def verify_crm(sheets, sid, expected):
    values = sheets.spreadsheets().values().get(spreadsheetId=sid,
        range="'Налаштування'!A2:B30").execute().get("values", [])
    settings = {r[0]: r[1] for r in values if len(r) >= 2}
    if settings.get("Основна пошта", "").strip().lower() != expected.strip().lower():
        raise ValueError("CRM identity mismatch")
    if not settings.get("Прайс Drive ID"):
        raise ValueError("Price ID missing in CRM")
    return settings

def load_price(drive, file_id):
    metadata = drive.files().get(fileId=file_id, fields="name,mimeType,size,trashed").execute()
    if (metadata.get("trashed") or metadata.get("mimeType") != "application/pdf"
        or int(metadata.get("size", "0")) != 556589):
        raise ValueError("Price metadata mismatch; review price configuration")
    stream = io.BytesIO()
    downloader = MediaIoBaseDownload(stream, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    content = stream.getvalue()
    if len(content) != 556589 or not content.startswith(b"%PDF-"):
        raise ValueError("Price content mismatch")
    return content

def imap_preflight():
    address = validate_sender(os.environ["EMAIL_ADDRESS"], os.environ["EXPECTED_GMAIL"])
    with imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context(), timeout=30) as conn:
        conn.login(address, os.environ["EMAIL_APP_PASSWORD"])
        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("IMAP read-only inbox unavailable")
    print("IMAP_READ_ONLY_OK")

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
        print("CHECK_ERROR", mode, type(exc).__name__)
        raise SystemExit(1)
