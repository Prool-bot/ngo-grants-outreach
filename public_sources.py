"""Read-only, keyless official procurement sources. No contact data collected."""
import re
from datetime import datetime, timedelta
import requests

PROZORRO = "https://public-api.prozorro.gov.ua/api/2.5/tenders"
TED = "https://api.ted.europa.eu/v3/notices/search"
HEADERS = {"User-Agent": "NGOGrantsResearch/0.2 (+https://github.com/Prool-bot/ngo-grants-outreach)"}
CPV_PREFIXES = ("79341", "79342", "79416", "79340000")
ACTIVE = {"active.tendering", "active.enquiries"}

def parse_prozorro_detail(record):
    data = record.get("data", {})
    identifier = str(data.get("tenderID", ""))
    if not re.fullmatch(r"UA-\d{4}-\d{2}-\d{2}-\d{6}-[a-z]", identifier):
        return None
    if data.get("status") not in ACTIVE:
        return None
    codes = [str(x.get("classification", {}).get("id", "")) for x in data.get("items", [])]
    title = str(data.get("title", ""))
    if not title or not any(c.startswith(CPV_PREFIXES) for c in codes):
        return None
    buyer = str(data.get("procuringEntity", {}).get("name", ""))
    return {"title": title, "url": "https://prozorro.gov.ua/tender/" + identifier,
            "buyer": buyer, "deadline": data.get("tenderPeriod", {}).get("endDate", ""),
            "published": data.get("date", ""), "subject": ", ".join(codes)}

def prozorro_notices(limit=25):
    response = requests.get(PROZORRO, params={"descending": 1, "limit": limit,
        "opt_fields": "status,tenderID"}, headers=HEADERS, timeout=25)
    response.raise_for_status()
    result = []
    for item in response.json()["data"]:
        if item.get("status") not in ACTIVE:
            continue
        identifier = item.get("id", "")
        if not re.fullmatch(r"[0-9a-f]{32}", identifier):
            continue
        r = requests.get(f"{PROZORRO}/{identifier}", headers=HEADERS, timeout=20)
        r.raise_for_status()
        notice = parse_prozorro_detail(r.json())
        if notice:
            result.append(notice)
    return result

def field_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "; ".join(filter(None, (field_text(v) for v in value)))
    if isinstance(value, dict):
        for lang in ("ENG", "eng", "en", "UKR", "ukr", "uk"):
            if value.get(lang):
                return field_text(value[lang])
        return next((field_text(v) for v in value.values() if v), "")
    return ""

def parse_ted_notice(item):
    number = field_text(item.get("publication-number"))
    title = field_text(item.get("notice-title"))
    if not re.fullmatch(r"\d{1,8}-\d{4}", number) or not title:
        return None
    return {"title": title, "url": f"https://ted.europa.eu/en/notice/-/detail/{number}",
        "buyer": field_text(item.get("buyer-name")),
        "published": field_text(item.get("publication-date")), "deadline": field_text(item.get("deadline-receipt-request")),
        "subject": field_text(item.get("classification-cpv"))}

def ted_notices(day):
    since = (day - timedelta(days=7)).strftime("%Y%m%d")
    codes = " OR ".join("classification-cpv=" + c for c in ("79341000", "79342000", "79416000"))
    body = {"query": f"publication-date>={since} AND form-type=competition AND deadline-receipt-request>={day.strftime('%Y%m%d')} AND ({codes})",
        "fields": ["publication-number", "notice-title", "buyer-name", "publication-date", "classification-cpv", "deadline-receipt-request"],
        "page": 1, "limit": 50, "scope": "ACTIVE", "paginationMode": "PAGE_NUMBER"}
    response = requests.post(TED, headers=HEADERS, json=body, timeout=30)
    response.raise_for_status()
    return [x for n in response.json()["notices"] if (x := parse_ted_notice(n)) and x["deadline"]]

if __name__ == "__main__":
    failures = 0
    for name, action in [("Prozorro", prozorro_notices), ("TED", lambda: ted_notices(datetime.now().date()))]:
        try:
            print(name, "OK", "count", len(action()))
        except requests.HTTPError as e:
            print(name, "ERROR", "HTTP", e.response.status_code)
            failures += 1
        except Exception as e:
            print(name, "ERROR", type(e).__name__)
            failures += 1
    raise SystemExit(bool(failures))
