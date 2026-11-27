"""Independent public-knowledge catalog. No contacts, external websites, CRM or mail access."""
from __future__ import annotations
import argparse
import csv
import json
import math
import re
import time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parent
API="https://uk.wikipedia.org/w/api.php"
HEADERS={"User-Agent":"NGOGrantsKnowledgeCatalog/1.0 (+https://github.com/Prool-bot/ngo-grants-outreach)"}
GROUPS={"NGO":20,"FIN":12,"EDU":15,"ART":20,"BUS":17,"MED":17,"DEV":14}
ORG_RE=re.compile(r"організаці|установ|компані|підприємств|фонд|банк|університет|коледж|школ|академі|інститут|агенц|агентств|асоціац|товариств|спілк|платформ|центр|музе|галере|театр|видавництв|студі|бюро|магазин|книгар|медіа|виданн|сервіс|провайдер|бренд|палат|посольств|представництв|програм|проєкт|резиденц|хаб|інкубатор|акселератор|бібліотек|радіостанц|телеканал|журнал|газет|фестиваль",re.I)
PERSON_RE=re.compile(r"бізнесмен|підприємець|підприємиця|політик|письменник|письменниця|фотограф|актор|співак|художник|художниця|науковець|вчений|вчена|журналіст|режисер|архітектор|викладач|економіст|народився|народилася",re.I)
EXCLUDED=re.compile(r"аграр|сільськогосподар|agricultur|agronom",re.I)

def load_categories():
    rows=json.loads((ROOT/"categories.json").read_text(encoding="utf-8"))
    expected={f"{g}-{n:02d}" for g,count in GROUPS.items() for n in range(1,count+1)}
    if len(rows)!=115 or {r["code"] for r in rows}!=expected or any(
        r["group"]!=r["code"].split("-")[0] or not r["query"] or not r["label"] for r in rows
    ):
        raise ValueError("Classifier must contain exactly the 115 unique original categories")
    return rows

def matching_tokens(text, query):
    tokens=re.findall(r"[а-яіїєґa-z0-9]+",query.casefold())
    tokens=[w for w in tokens if len(w)>=2]
    if not tokens:
        return False
    # Conservative fuzzy match for Ukrainian inflection; no claim of verified classification.
    return sum((w[:max(2,len(w)-3)] in text) for w in tokens)>=max(1,math.ceil(len(tokens)*.67))

def select_reference(page, cat):
    if page.get("ns")!=0:
        return None
    props=page.get("pageprops",{})
    qid=props.get("wikibase_item","")
    if not re.fullmatch(r"Q[1-9]\d*",qid) or "disambiguation" in props:
        return None
    title=str(page.get("title","")).strip()
    descriptions=page.get("terms",{}).get("description",[])
    description=str(descriptions[0]).strip() if descriptions else ""
    if not title or not description or PERSON_RE.search(description) or EXCLUDED.search(title+" "+description):
        return None
    if title.casefold().startswith(("список ","перелік ","історія ")):
        return None
    if not ORG_RE.search(description) or not matching_tokens((title+" "+description).casefold(),cat["query"]):
        return None
    return {
        "category_code":cat["code"],"category":cat["label"],
        "title":title,"source_id":qid,
        "source_url":"https://www.wikidata.org/wiki/"+qid,
        "status":"REFERENCE_REVIEW_REQUIRED"
    }

def search_category(session, cat, offset=0):
    params={"action":"query","format":"json","formatversion":2,"maxlag":5,
        "generator":"search","gsrsearch":cat["query"]+" Україна","gsrnamespace":0,
        "gsrlimit":10,"gsroffset":offset,"prop":"pageprops|pageterms","wbptterms":"description"}
    response=session.get(API,params=params,headers=HEADERS,timeout=(8,18))
    if response.status_code in (429,503):
        raise RuntimeError("SOURCE_PAUSE")
    response.raise_for_status()
    data=response.json()
    if "error" in data:
        if data["error"].get("code")=="maxlag":
            raise RuntimeError("SOURCE_PAUSE")
        raise RuntimeError("API_ERROR")
    pages=data.get("query",{}).get("pages",[])
    refs={}
    for page in pages:
        row=select_reference(page,cat)
        if row:
            refs.setdefault(row["source_id"],row)
    return len(pages),list(refs.values())

def csv_cell(value):
    value=str(value)
    return "'"+value if value.startswith(("=","+","-","@","\t","\r")) else value

def write_csv(path, fields, rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows({k:csv_cell(r.get(k,"")) for k in fields} for r in rows)

def run(output, group=None, offset=0):
    categories=load_categories()
    if group:
        categories=[r for r in categories if r["group"]==group]
    output.mkdir(parents=True,exist_ok=True)
    summary=[]
    refs=[]
    paused=False
    with requests.Session() as session:
        for cat in categories:
            row={**cat,"raw_results":0,"references":0,"status":"NOT_ATTEMPTED","offset":offset}
            if not paused:
                try:
                    raw,found=search_category(session,cat,offset)
                    refs.extend(found)
                    row.update(raw_results=raw,references=len(found),status="SEARCHED_WITH_REFERENCES" if found else "SEARCHED_NO_REFERENCES")
                except Exception as exc:
                    row["status"]="SOURCE_ERROR"
                    row["error"]=type(exc).__name__
                    # Honor overload and connection failure; do not hammer source.
                    if str(exc)=="SOURCE_PAUSE" or isinstance(exc,requests.exceptions.RequestException):
                        paused=True
                time.sleep(.2)
            summary.append(row)
    # Category-to-reference links can legitimately repeat. Unique reference catalog deduplicates by QID.
    unique={}
    for ref in refs:
        u=unique.setdefault(ref["source_id"],{k:ref[k] for k in ("title","source_id","source_url","status")}|{"category_codes":[]})
        if ref["category_code"] not in u["category_codes"]:
            u["category_codes"].append(ref["category_code"])
    write_csv(output/"category_coverage.csv",["code","group","label","query","offset","raw_results","references","status","error"],summary)
    write_csv(output/"catalog.csv",["title","source_id","source_url","category_codes","status"],
              [{**r,"category_codes":"; ".join(r["category_codes"])} for r in unique.values()])
    (output/"catalog.json").write_text(json.dumps({"coverage":summary,"references":list(unique.values())},ensure_ascii=False,indent=2),encoding="utf-8")
    searched=sum(r["status"].startswith("SEARCHED") for r in summary)
    populated=sum(r["status"]=="SEARCHED_WITH_REFERENCES" for r in summary)
    print("CATALOG_CONFIGURED",len(categories),"SEARCHED",searched,"WITH_REFERENCES",populated,"UNIQUE_REFERENCES",len(unique))
    return 0 if searched==len(categories) else 1

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--group",choices=list(GROUPS))
    parser.add_argument("--output",type=Path,default=Path("catalog-output"))
    parser.add_argument("--offset",type=int,choices=range(0,50,10),default=0)
    args=parser.parse_args()
    raise SystemExit(run(args.output,args.group,args.offset))
