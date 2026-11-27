"""Public research institution directory. No emails or individual contacts.
ROR entries are leads for research, not verified partners or consent.
"""
import re
from urllib.parse import urlsplit
import requests
from public_sources import HEADERS

ROR = "https://api.ror.org/v2/organizations"
QUERIES = [
    ("university", "education", "EDU-01"),
    ("research institute", "facility", "EDU-07"),
    ("foundation", "funder", "NGO-12"),
]
def parse_record(item, code):
    rid = str(item.get("id", ""))
    if not re.fullmatch(r"https://ror\.org/0[0-9a-z]{8}", rid) or item.get("status") != "active":
        return None
    if not any(loc.get("geonames_details", {}).get("country_code") == "UA"
               for loc in item.get("locations", [])):
        return None
    names = item.get("names", [])
    name = next((n.get("value", "") for n in names if n.get("lang") == "uk" and "label" in n.get("types", [])), "")
    name = name or next((n.get("value", "") for n in names if "ror_display" in n.get("types", [])), "")
    if not name:
        return None
    # Exclude agricultural direction; uncertain institutions still require review.
    if re.search(r"аграр|сільськогосподар|agricultur|agronom", name, re.I):
        return None
    website = next((x.get("value", "") for x in item.get("links", [])
                    if x.get("type") == "website" and urlsplit(x.get("value", "")).scheme in {"http","https"}), "")
    return {"id":rid, "name":name, "code":code, "website":website,
            "types":", ".join(item.get("types", []))}
def directory_entries(now, limit=50):
    results = {}
    stats = {}
    # Rotate bounded pages; this is not a complete registry export.
    for query, kind, code in QUERIES:
        params = {"query": query, "filter": f"country.country_code:UA,types:{kind}", "page": 1}
        r = requests.get(ROR, params=params, headers=HEADERS, timeout=25)
        r.raise_for_status()
        data = r.json()
        total = int(data.get("number_of_results", 0))
        pages = min(20, max(1, (total + 19)//20))
        page = 1 + (now.toordinal()*9 + max(0, now.hour-9)) % pages
        if page != 1:
            params["page"] = page
            r = requests.get(ROR, params=params, headers=HEADERS, timeout=25)
            r.raise_for_status()
            data = r.json()
        count = 0
        for item in data.get("items", []):
            if kind not in item.get("types", []):
                continue
            row = parse_record(item, code)
            if row and row["id"] not in results:
                results[row["id"]] = row
                count += 1
        stats[code] = {"results": total, "page": page, "found": count}
    return list(results.values())[:limit], stats
