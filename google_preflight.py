"""Verify Google Sheets registry access. No mail or price-file access."""
import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def file_services():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    expected_service = os.environ.get("EXPECTED_SERVICE_ACCOUNT", "").strip().lower()
    if expected_service and info.get("client_email", "").lower() != expected_service:
        raise ValueError("Service account identity mismatch")
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    print("SERVICE_ACCOUNT_CONFIG_OK", flush=True)
    return (build("sheets", "v4", credentials=creds, cache_discovery=False),
            None)

def verify_crm(sheets, sid, expected):
    print("STAGE CRM_READ", flush=True)
    values = sheets.spreadsheets().values().get(spreadsheetId=sid,
        range="'Налаштування'!A2:B30").execute().get("values", [])
    settings = {r[0]: r[1] for r in values if len(r) >= 2}
    if settings.get("Основна пошта", "").strip().lower() != expected.strip().lower():
        raise ValueError("CRM identity mismatch")
    print("CRM_READ_OK", flush=True)
    return settings

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

