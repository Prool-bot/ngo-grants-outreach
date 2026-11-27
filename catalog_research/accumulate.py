"""Accumulate public reference IDs across runs, independently of the CRM."""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from catalog_research.run import load_categories, write_csv

def merge(previous, current, stamp):
    codes={r["code"] for r in load_categories()}
    refs={}
    for snapshot, historical in ((previous,True),(current,False)):
        for r in snapshot.get("references",[]):
            qid=r.get("source_id","")
            title=str(r.get("title","")).strip()
            tags=set(r.get("category_codes",[])) & codes
            if not re.fullmatch(r"Q[1-9]\d*",qid) or not title or not tags:
                continue
            entry=refs.setdefault(qid,{"source_id":qid,"title":title,
                "source_url":"https://www.wikidata.org/wiki/"+qid,
                "category_codes":[],"status":"REFERENCE_REVIEW_REQUIRED",
                "first_seen":r.get("first_seen","") if historical else stamp,
                "last_seen":r.get("last_seen","") if historical else stamp})
            entry["category_codes"]=sorted(set(entry["category_codes"])|tags)
            if not historical:
                entry["last_seen"]=stamp
                entry["title"]=title
    return list(sorted(refs.values(),key=lambda r:r["source_id"]))

def accumulate(previous, current, stamp):
    refs=merge(previous,current,stamp)
    before=Counter(c for r in previous.get("references",[]) for c in set(r.get("category_codes",[])))
    after=Counter(c for r in refs for c in r["category_codes"])
    latest={r["code"]:r for r in current.get("coverage",[])}
    summary=[]
    for cat in load_categories():
        code=cat["code"]
        state=latest.get(code,{})
        summary.append({"code":code,"group":cat["group"],"label":cat["label"],
            "cumulative":after[code],"previous":before[code],"growth":after[code]-before[code],
            "last_search_status":state.get("status","NOT_ATTEMPTED"),
            "last_search_results":state.get("references",0)})
    return {"as_of":stamp,"coverage":summary,"references":refs}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--current",type=Path,required=True)
    p.add_argument("--previous",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    previous=json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else {}
    current=json.loads(args.current.read_text(encoding="utf-8"))
    result=accumulate(previous,current,datetime.now(timezone.utc).isoformat(timespec="seconds"))
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"cumulative.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    write_csv(args.output/"cumulative_catalog.csv",["source_id","title","source_url","category_codes","status","first_seen","last_seen"],
        [{**r,"category_codes":"; ".join(r["category_codes"])} for r in result["references"]])
    write_csv(args.output/"cumulative_coverage.csv",["code","group","label","cumulative","previous","growth","last_search_status","last_search_results"],result["coverage"])
    print("CUMULATIVE_REFERENCES",len(result["references"]),"COVERED_CATEGORIES",sum(r["cumulative"]>0 for r in result["coverage"]),"NEW_REFERENCES",len(result["references"])-len(previous.get("references",[])))

if __name__=="__main__":
    main()
