"""Non-destructive review of existing procurement rows.
Only machine-generated, unreviewed statuses may be updated.
Never modifies contacts, reviewed eligibility or manual decisions.
"""
import os
from collections import Counter
from datetime import datetime
from outreach import ZONE, read_values
from google_preflight import file_services, verify_crm
from procurement_quality import triage

MACHINE_STATES={"NEW","UNVERIFIED_DEADLINE","VERIFY_ELIGIBILITY","VERIFY_TODAY",
                "EXPIRED","LOW_RELEVANCE","EXCLUDED_SECTOR","EXCLUDED_NAVIGATION"}

def plan(rows,today):
    updates=[]
    counts=Counter()
    for index,row in enumerate(rows,2):
        if not row or not row[0]:
            continue
        r=list(row)+[""]*max(0,11-len(row))
        status,reason=triage(r[3],r[5],r[7],today)
        counts[status]+=1
        if r[9] in MACHINE_STATES and r[9]!=status:
            updates.append((index,r[0],r[9],status,reason))
    return updates,counts

def run(apply=False):
    sheets,_=file_services()
    sid=os.environ["CRM_ID"]
    verify_crm(sheets,sid,os.environ["EXPECTED_GMAIL"])
    values=sheets.spreadsheets().values()
    rows=read_values(sheets,sid,"'Закупівлі'!A2:K")
    updates,counts=plan(rows,datetime.now(ZONE).date())
    print("REGISTRY_AUDIT",dict(counts),"PROPOSED_UPDATES",len(updates))
    if not apply or not updates:
        return
    # Detect a concurrent manual edit before touching the row.
    fresh=read_values(sheets,sid,"'Закупівлі'!A2:K")
    if fresh!=rows:
        raise RuntimeError("Registry changed during audit; no edits made")
    data=[]
    for index,identifier,old,status,reason in updates:
        data.append({"range":f"'Закупівлі'!J{index}:K{index}",
                     "values":[[status,reason+"; потрібна ручна оцінка; не підстава для реклами"]]})
    values.batchUpdate(spreadsheetId=sid,body={"valueInputOption":"RAW","data":data}).execute()
    result=read_values(sheets,sid,"'Закупівлі'!A2:K")
    if not all(len(result[i-2])>=10 and result[i-2][0]==k and result[i-2][9]==s for i,k,_,s,_ in updates):
        raise RuntimeError("Registry audit readback failed")
    print("REGISTRY_AUDIT_APPLIED",len(updates))

if __name__=="__main__":
    import sys
    try:
        run("--apply" in sys.argv)
    except Exception as e:
        print("REGISTRY_AUDIT_ERROR",type(e).__name__)
        raise SystemExit(1)
