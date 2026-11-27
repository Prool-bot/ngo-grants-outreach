"""Read-only review of expressly requested or opted-in individual correspondence.
Does not send messages, infer consent or move rows into a sending queue.
"""
import os, re
from collections import Counter
from datetime import date
from outreach import read_values
from google_preflight import file_services, verify_crm

def address(value):
    return str(value).strip().casefold()

def evaluate(rows, blocked, previously_used, today):
    counts=Counter()
    seen=set()
    for row in rows:
        if not row:
            continue
        if len(row)<8:
            counts["INCOMPLETE"]+=1
            continue
        addr=address(row[3])
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",addr):
            counts["INVALID_ADDRESS"]+=1
        elif addr in blocked or addr in previously_used:
            counts["EXCLUDED"]+=1
        elif addr in seen:
            counts["DUPLICATE"]+=1
        elif row[7]!="APPROVED":
            counts["NEEDS_REVIEW"]+=1
        elif row[4] not in {"EXPLICIT_OPT_IN","DIRECT_REQUEST"} or not str(row[5]).strip():
            counts["EVIDENCE_MISSING"]+=1
        else:
            try:
                age=(today-date.fromisoformat(str(row[6])[:10])).days
                if not 0<=age<=30:
                    raise ValueError
            except ValueError:
                counts["RECHECK_DATE"]+=1
                continue
            counts["REVIEWABLE"]+=1
        seen.add(addr)
    return counts

def run():
    sheets,_=file_services()
    sid=os.environ["CRM_ID"]
    verify_crm(sheets,sid,os.environ["EXPECTED_GMAIL"])
    blocked=set()
    for tab in ("Відмови","Недійсні","Повернення"):
        blocked.update(address(r[0]) for r in read_values(sheets,sid,f"'{tab}'!A2:A") if r)
    prior=set()
    # Conservative: exclude any legacy or current recorded contact, regardless of outcome.
    for tab in ("Історія розсилок","Контрагенти"):
        prior.update(address(r[0]) for r in read_values(sheets,sid,f"'{tab}'!D2:D") if r)
    queue=read_values(sheets,sid,"'Черга'!A2:K")
    counts=evaluate(queue,blocked,prior,date.today())
    print("QUEUE_AUDIT",dict(counts))

if __name__=="__main__":
    try:
        run()
    except Exception as e:
        print("QUEUE_AUDIT_ERROR",type(e).__name__)
        raise SystemExit(1)
