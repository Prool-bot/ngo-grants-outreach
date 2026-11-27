"""Reconcile confirmed invalid addresses from the existing delivery-failure register.
No discovery of addresses, no mail transmission, no changes to previous records.
"""
import os
import re
from outreach import read_values, append_values
from google_preflight import file_services, verify_crm
from queue_audit import address

def plan(returns, invalid):
    seen={address(r[0]) for r in invalid if r}
    result=[]
    for r in returns:
        if len(r)<7 or not r[5] or not r[0]:
            continue
        addr=address(r[0])
        if addr in seen or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",addr):
            continue
        if "Виключити" not in r[6]:
            continue
        if not (re.search(r"\b5\.1\.1\b",r[3]) or re.search(r"no such user|email account does not exist",r[4],re.I)):
            continue
        seen.add(addr)
        result.append([r[0],r[1],r[2],r[3]+" — "+r[4],r[5],"Не надсилати; за наявним журналом повернень"])
    return result

def run():
    sheets,_=file_services()
    sid=os.environ["CRM_ID"]
    verify_crm(sheets,sid,os.environ["EXPECTED_GMAIL"])
    returns=read_values(sheets,sid,"'Повернення'!A2:G")
    invalid=read_values(sheets,sid,"'Недійсні'!A2:F")
    rows=plan(returns,invalid)
    if rows:
        fresh=read_values(sheets,sid,"'Недійсні'!A2:F")
        rows=plan(returns,fresh)
        append_values(sheets,sid,"'Недійсні'!A:F",rows)
        verified={address(r[0]) for r in read_values(sheets,sid,"'Недійсні'!A2:A") if r}
        if not all(address(r[0]) in verified for r in rows):
            raise RuntimeError("Invalid-address readback failed")
    print("DELIVERY_REGISTER_OK",len(returns),"NEW_INVALID",len(rows))

if __name__=="__main__":
    try:
        run()
    except Exception as e:
        print("DELIVERY_REGISTER_ERROR",type(e).__name__)
        raise SystemExit(1)
