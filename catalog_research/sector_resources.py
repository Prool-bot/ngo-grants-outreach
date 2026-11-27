"""Sector information resources, not a counterparty or contact directory.
Collect public notices, dataset metadata, cultural events and bibliography only.
"""
import argparse
from collections import Counter
from datetime import date,timedelta,datetime,timezone
import json
from pathlib import Path
import re
from urllib.parse import quote
import requests
from catalog_research.run import HEADERS,write_csv

TED="https://api.ted.europa.eu/v3/notices/search"
HDX="https://data.humdata.org/api/3/action/package_search"
MB="https://musicbrainz.org/ws/2/event"
CROSSREF="https://api.crossref.org/works"
AIC="https://api.artic.edu/api/v1/artworks/search"
CPV={
    "HYGIENE":("337*","3983*"),
    "MEDICAL":("331*","336*"),
    "ART_SUPPLIES":("378*","3865*"),
    "MUSIC_SUPPLIES":("373*",),
    "HUMANITARIAN_SUPPLIES":("3951*","358*","44211100","42912300"),
    "LOGISTICS":("600*","601*","631*","641*"),
    "ENERGY":("3112*","0933*","314*"),
    "CULTURE_SPORT":("923*","926*"),
}
PAPERS={"DROPSHIPPING":"dropshipping business model",
        "ECOMMERCE":"e-commerce platforms digital retail",
        "HUMANITARIAN_PROCUREMENT":"humanitarian procurement supply chain",
        "TOURISM":"sustainable tourism cultural heritage",
        "CREATIVE_INDUSTRIES":"creative industries arts entrepreneurship"}
UUID=r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"

def text_value(x):
    if isinstance(x,str):
        return x
    if isinstance(x,list):
        return next((t for v in x if (t:=text_value(v))),"")
    if isinstance(x,dict):
        return next((t for k in ("ENG","UKR","eng","ukr","en","uk") if (t:=text_value(x.get(k)))),"") or next((t for v in x.values() if (t:=text_value(v))),"")
    return ""

def row(source, identifier, title, topic, kind, url, published="", deadline=""):
    if not title or not identifier:
        return None
    return {"source":source,"source_id":identifier,"title":title[:500],"topics":[topic],
            "kind":kind,"source_url":url,"published":published,"deadline":deadline,
            "status":"REVIEW_REQUIRED"}

def ted(s, topic, codes, today):
    query=" OR ".join("classification-cpv="+c for c in codes)
    body={"query":f"publication-date>={(today-timedelta(days=7)).strftime('%Y%m%d')} AND form-type=competition AND deadline-receipt-request>={today.strftime('%Y%m%d')} AND ({query})",
          "fields":["publication-number","notice-title","publication-date","deadline-receipt-request"],
          "page":1,"limit":20,"scope":"ACTIVE","paginationMode":"PAGE_NUMBER"}
    resp=s.post(TED,json=body,headers=HEADERS,timeout=(8,25))
    resp.raise_for_status()
    data=resp.json()
    result=[]
    for item in data["notices"]:
        number=text_value(item.get("publication-number"))
        deadline=text_value(item.get("deadline-receipt-request"))
        if not re.fullmatch(r"\d{1,8}-\d{4}",number) or not deadline:
            continue
        r=row("TED",number,text_value(item.get("notice-title")),topic,"PROCUREMENT_NOTICE",
            "https://ted.europa.eu/en/notice/-/detail/"+number,text_value(item.get("publication-date")),deadline)
        if r:
            result.append(r)
    return result

def get(s,url,params):
    resp=s.get(url,params=params,headers=HEADERS,timeout=(8,22))
    resp.raise_for_status()
    return resp.json()

def hdx(s,topic,query):
    data=get(s,HDX,{"q":query,"fq":"groups:ukr","rows":10,"sort":"metadata_modified desc"})
    if not data.get("success"):
        raise ValueError("HDX search unsuccessful")
    result=[]
    for item in data["result"]["results"]:
        identifier=str(item.get("id",""))
        slug=str(item.get("name",""))
        if item.get("private") or not re.fullmatch(UUID,identifier) or not re.fullmatch(r"[a-z0-9_-]+",slug):
            continue
        r=row("HDX",identifier,str(item.get("title","")),topic,"DATASET",
              "https://data.humdata.org/dataset/"+slug,str(item.get("metadata_modified","")))
        if r:
            result.append(r)
    return result

def music(s,offset):
    result=[]
    data=get(s,MB,{"query":"area:Ukraine AND (type:Festival OR type:Concert)","fmt":"json","limit":10,"offset":offset})
    for item in data["events"]:
        identifier=str(item.get("id",""))
        if not re.fullmatch(UUID,identifier) or item.get("cancelled"):
            continue
        r=row("MusicBrainz",identifier,str(item.get("name","")),"MUSIC_CULTURE","EVENT_REFERENCE",
              "https://musicbrainz.org/event/"+identifier,str(item.get("life-span",{}).get("begin","")))
        if r:
            result.append(r)
    return result

def art(s,offset):
    data=get(s,AIC,{"q":"Ukraine","fields":"id,title,date_display","limit":10,"page":1+offset//10})
    return [r for item in data["data"] if str(item.get("id","")).isdigit()
            if (r:=row("ArtIC",str(item["id"]),str(item.get("title","")),"VISUAL_ART","ARTWORK_REFERENCE",
                "https://www.artic.edu/artworks/"+str(item["id"]),str(item.get("date_display",""))))]

def papers(s,topic,query,offset):
    data=get(s,CROSSREF,{"query.bibliographic":query,"rows":8,"offset":offset,"select":"DOI,title,published"})
    result=[]
    for item in data["message"]["items"]:
        doi=str(item.get("DOI","")).lower()
        if not re.fullmatch(r"10\.\d{4,9}/[^\s<>]+",doi):
            continue
        title=text_value(item.get("title"))
        parts=item.get("published",{}).get("date-parts",[])
        year=str(parts[0][0]) if parts and parts[0] else ""
        r=row("Crossref-works",doi,title,topic,"BIBLIOGRAPHY","https://doi.org/"+quote(doi,safe="/"),year)
        if r:
            result.append(r)
    return result

def merge(previous,current):
    combined={}
    for items in (previous,current):
        for r in items:
            key=(r["source"],r["source_id"])
            before=combined.get(key)
            tags=set(r["topics"])|set(before["topics"] if before else [])
            combined[key]={**r,"topics":sorted(tags)}
    return list(combined.values())

def run(output,previous,offset):
    now=datetime.now(timezone.utc)
    today=now.date()
    records=[]
    stats=[]
    with requests.Session() as s:
        actions=[("TED",t,lambda t=t,c=c:ted(s,t,c,today)) for t,c in CPV.items()]
        actions += [("HDX",t,lambda t=t,q=q:hdx(s,t,q)) for t,q in (
            ("HUMANITARIAN_NEEDS","humanitarian"),("WASH","water sanitation hygiene"),("DISPLACEMENT","displacement"))]
        actions += [("MusicBrainz","MUSIC_CULTURE",lambda:music(s,offset)),("ArtIC","VISUAL_ART",lambda:art(s,offset))]
        actions += [("Crossref-works",t,lambda t=t,q=q:papers(s,t,q,offset)) for t,q in PAPERS.items()]
        paused=set()
        for source,topic,action in actions:
            state={"source":source,"topic":topic,"status":"NOT_ATTEMPTED","found":0}
            if source not in paused:
                try:
                    found=action()
                    records.extend(found)
                    state.update(status="OK",found=len(found))
                except Exception as exc:
                    state.update(status="ERROR",error=type(exc).__name__)
                    if isinstance(exc,requests.exceptions.RequestException):
                        paused.add(source)
            stats.append(state)
            print("SECTOR_SOURCE",source,topic,state["status"],state["found"],state.get("error",""),flush=True)
    prior=json.loads(previous.read_text(encoding="utf-8"))["records"] if previous and previous.exists() else []
    combined=merge(prior,records)
    output.mkdir(parents=True,exist_ok=True)
    (output/"sector_resources.json").write_text(json.dumps({"as_of":now.isoformat(),"records":combined,"sources":stats},ensure_ascii=False,indent=2),encoding="utf-8")
    write_csv(output/"sector_resources.csv",["source","source_id","title","topics","kind","source_url","published","deadline","status"],
        [{**r,"topics":"; ".join(r["topics"])} for r in combined])
    write_csv(output/"sector_sources.csv",["source","topic","status","found","error"],stats)
    counts=Counter(t for r in combined for t in r["topics"])
    write_csv(output/"sector_coverage.csv",["topic","cumulative"],[{"topic":t,"cumulative":counts[t]} for t in sorted({s["topic"] for s in stats})])
    print("SECTOR_CUMULATIVE",len(combined),"NEW",len(combined)-len(prior),"TOPICS",len(counts),"CONFIGURED",len(stats))
    return 0 if all(x["status"]=="OK" for x in stats) else 1

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--previous",type=Path)
    p.add_argument("--offset",type=int,default=0)
    a=p.parse_args()
    raise SystemExit(run(a.output,a.previous,a.offset))
