"""NGO Grants Outreach: procurement research and CRM connection check.
No email transmission or harvesting. Announcements require human review.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo
from urllib.robotparser import RobotFileParser
from public_sources import prozorro_notices, ted_notices
from directory_sources import directory_entries
from procurement_quality import triage

ZONE = ZoneInfo("Europe/Istanbul")
SOURCES = {
    "Громадський Простір": "https://www.prostir.ua/category/grants/?tenders=1",
    "ГУРТ": "https://www.gurt.org.ua/news/grants/",
}
USER_AGENT = "NGOGrantsResearch/0.1"
KEYWORDS = re.compile(r"тендер|закупівл|закупов|цінов\w* пропозиц|запит пропозиц", re.I)

def is_work_hour(now: datetime) -> bool:
    t = now.astimezone(ZONE)
    return t.weekday() < 5 and 9 <= t.hour <= 17

def canonical_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    host = p.hostname.lower().removeprefix("www.")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit(("https", host, p.path.rstrip("/") or "/", urlencode(sorted(q)), ""))

def parse_listing(html: str, base: str) -> list[tuple[str, str]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    base_host = urlsplit(base).hostname.lower().removeprefix("www.")
    for a in soup.find_all("a", href=True):
        title = " ".join(a.stripped_strings)
        if len(title) < 12 or not KEYWORDS.search(title) or re.search(r"правила публікаці|як опублікувати|архів тендерів", title, re.I):
            continue
        target = canonical_url(urljoin(base, a["href"]))
        if not target or urlsplit(target).hostname != base_host or target == canonical_url(base):
            continue
        p = urlsplit(target)
        if p.path.startswith("/category/") or p.path.rstrip("/") in ("/news", ""):
            if not any(k in {"grants", "jobs"} for k, _ in parse_qsl(p.query)):
                continue
        results.setdefault(target, title)
    return [(title, url) for url, title in results.items()]

def fetch_listing(url: str) -> str:
    import requests
    base = urlsplit(url)
    robots_url = f"{base.scheme}://{base.netloc}/robots.txt"
    robots = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=15)
    if robots.status_code == 404:
        pass
    elif robots.ok:
        rp = RobotFileParser()
        rp.parse(robots.text.splitlines())
        if not rp.can_fetch(USER_AGENT, url):
            raise RuntimeError("robots.txt не дозволяє доступ")
    else:
        raise RuntimeError(f"robots.txt HTTP {robots.status_code}; пропуск джерела")
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    if urlsplit(r.url).hostname.lower().removeprefix("www.") != base.hostname.lower().removeprefix("www."):
        raise RuntimeError("Перенаправлення за межі джерела")
    return r.text

def read_values(service, sheet_id, range_):
    return service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_).execute().get("values", [])

def append_values(service, sheet_id, range_, rows):
    if rows:
        return service.spreadsheets().values().append(
            spreadsheetId=sheet_id, range=range_, valueInputOption="RAW",
            insertDataOption="INSERT_ROWS", body={"values": rows}).execute()

def run(mode: str) -> int:
    from google_preflight import file_services, verify_crm, load_price
    from smtp_preflight import validate_sender
    sid = os.environ["CRM_ID"]
    expected = os.environ["EXPECTED_GMAIL"].strip().lower()
    now = datetime.now(ZONE)
    cycle = now.strftime("%Y-%m-%dT%H:00%z")
    if mode == "monitor" and not is_work_hour(now):
        print("SKIPPED: outside work hours")
        return 0
    start = now.isoformat(timespec="seconds")
    validate_sender(os.environ["EMAIL_ADDRESS"], expected)
    sheets, drive = file_services()
    config = verify_crm(sheets, sid, expected)
    print("STAGE PROCUREMENT_READ", flush=True)
    history = read_values(sheets, sid, "'Закупівлі'!A2:K")
    seen = {canonical_url(r[6]) for r in history if len(r) > 6}
    if mode == "check":
        load_price(drive, config["Прайс Drive ID"])
        test_id = "CHECK-" + hashlib.sha256((start + os.getenv("GITHUB_RUN_ID", "")).encode()).hexdigest()[:20]
        print("STAGE CRM_WRITE_TEST", flush=True)
        append_values(sheets, sid, "'Системний журнал'!A:J",
            [[test_id, cycle, start, datetime.now(ZONE).isoformat(timespec="seconds"),
              "FILE_ACCESS_TEST", "OK", 0, 0, "", ""]])
        print("STAGE CRM_WRITE_READBACK", flush=True)
        if not any(r and r[0] == test_id for r in read_values(sheets, sid, "'Системний журнал'!A2:A")):
            raise RuntimeError("CRM test write not confirmed")
        print("PASS: CRM read/write, price download and register accessible; no external email")
        return 0
    previous = read_values(sheets, sid, "'Системний журнал'!A2:F")
    if mode == "monitor" and any(len(r) >= 6 and r[0] == cycle and r[5] == "OK" and r[4] == "DISCOVERY" for r in previous):
        print("SKIPPED: this cycle already succeeded")
        return 0
    new_rows, errors, source_stats = [], [], {}
    for name, url in SOURCES.items():
        try:
            found = parse_listing(fetch_listing(url), url)
            source_stats[name] = {"found": len(found), "new": 0}
            for title, link in found:
                if link in seen:
                    continue
                seen.add(link)
                source_stats[name]["new"] += 1
                key = hashlib.sha256(link.encode()).hexdigest()[:24]
                new_rows.append([key, "", name, title, "", "", link, "", "Потрібна оцінка", "UNVERIFIED_DEADLINE",
                    "Організатора, предмет і дедлайн перевірити; не є підставою для розсилки"])
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
            source_stats[name] = {"error": type(e).__name__}
    for name, action in [("Prozorro", prozorro_notices), ("TED", lambda: ted_notices(now.date()))]:
        try:
            notices = action()
            source_stats[name] = {"found": len(notices), "new": 0}
            for notice in notices:
                link = canonical_url(notice["url"])
                if not link or link in seen:
                    continue
                seen.add(link)
                source_stats[name]["new"] += 1
                key = hashlib.sha256(link.encode()).hexdigest()[:24]
                new_rows.append([key, notice["buyer"], name, notice["title"], notice["published"],
                    notice["deadline"], link, notice["subject"], "Потрібна оцінка", "VERIFY_ELIGIBILITY" if notice["deadline"] else "UNVERIFIED_DEADLINE",
                    "Офіційний API; перевірити умови та актуальність закупівлі"])
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
            source_stats[name] = {"error": type(e).__name__}
    existing = {canonical_url(r[6]) for r in read_values(sheets, sid, "'Закупівлі'!A2:K") if len(r)>6}
    from collections import Counter
    quality = Counter()
    rows = []
    for r in new_rows:
        status, reason = triage(r[3], r[5], r[7], now.date())
        quality[status] += 1
        if status in {"EXCLUDED_NAVIGATION", "EXCLUDED_SECTOR", "LOW_RELEVANCE", "EXPIRED"}:
            continue
        r[9] = status
        r[10] = reason + "; не є підставою для рекламної розсилки"
        if canonical_url(r[6]) not in existing:
            rows.append(r)
    source_stats["quality"] = dict(quality)
    candidates = []
    try:
        orgs, directory_stats = directory_entries(now)
        classifier = {r[0]: r[2] for r in read_values(sheets, sid, "'Класифікатор'!A2:E") if len(r)>=5 and r[4]=="Активна"}
        old = read_values(sheets, sid, "'Кандидати'!A2:K")
        known = {r[0] for r in old if r}
        known_names = {r[1].strip().casefold() for r in old if len(r)>1}
        for org in orgs:
            key = org["id"]
            name = org["name"]
            if org["code"] not in classifier or key in known or name.strip().casefold() in known_names:
                continue
            known.add(key)
            known_names.add(name.strip().casefold())
            candidates.append([key, name, "", org["code"]+" — "+classifier[org["code"]],
                org["website"], key, "ROR: "+org["types"], start, "Не встановлена",
                "RESEARCH_ONLY", "Категорія попередня; профіль і сайт потребують перевірки; не для автоматичної розсилки"])
        source_stats["ROR"] = {"found":len(orgs), "new":len(candidates), "categories":directory_stats}
    except Exception as e:
        errors.append("ROR: "+type(e).__name__)
        source_stats["ROR"] = {"error":type(e).__name__}
    if mode == "preview":
        print(json.dumps({"mode": "preview", "sources": source_stats, "new_announcements": len(rows),
                          "new_organizations":len(candidates), "sent": 0, "errors": errors}, ensure_ascii=False))
        return 1 if errors else 0
    if rows:
        append_values(sheets, sid, "'Закупівлі'!A:K", rows)
        ids = {r[0] for r in read_values(sheets, sid, "'Закупівлі'!A2:A") if r}
        if not all(r[0] in ids for r in rows):
            raise RuntimeError("CRM write readback failed")
    if candidates:
        existing_ids = {r[0] for r in read_values(sheets, sid, "'Кандидати'!A2:A") if r}
        candidates = [r for r in candidates if r[0] not in existing_ids]
        append_values(sheets, sid, "'Кандидати'!A:K", candidates)
        verified = {r[0] for r in read_values(sheets, sid, "'Кандидати'!A2:A") if r}
        if not all(r[0] in verified for r in candidates):
            raise RuntimeError("Candidate register readback failed")
    end = datetime.now(ZONE).isoformat(timespec="seconds")
    status = "PARTIAL" if errors and len(errors) < len(SOURCES) + 3 else "ERROR" if errors else "OK"
    run_url = f"{os.getenv('GITHUB_SERVER_URL','https://github.com')}/{os.getenv('GITHUB_REPOSITORY','')}/actions/runs/{os.getenv('GITHUB_RUN_ID','')}" if os.getenv("GITHUB_RUN_ID") else ""
    append_values(sheets, sid, "'Системний журнал'!A:J",
        [[cycle if mode=="monitor" else "PILOT-"+os.getenv("GITHUB_RUN_ID",start), cycle, start, end, "DISCOVERY" if mode=="monitor" else "PILOT", status, len(rows)+len(candidates), 0, "; ".join(errors), run_url]])
    print(json.dumps({"status": status, "sources": source_stats, "new_announcements": len(rows), "new_organizations":len(candidates), "sent": 0, "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "monitor", "preview", "pilot"], default="check")
    try:
        sys.exit(run(parser.parse_args().mode))
    except Exception as e:
        # Public Actions logs must not expose account data, OAuth errors or spreadsheet IDs.
        from googleapiclient.errors import HttpError
        from google_preflight import safe_http_error
        diagnostic = safe_http_error(e) if isinstance(e, HttpError) else type(e).__name__
        print(f"ERROR: {diagnostic}; verify secret configuration and API permissions", file=sys.stderr)
        sys.exit(1)
