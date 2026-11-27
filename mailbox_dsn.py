"""Read-only mailbox reconciliation of structured DSNs for existing CRM correspondence.
No messages are sent or modified. Ignore unknown recipients and unstructured mail.
"""
import email
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
import hashlib
import imaplib
import os
import re
import ssl
from datetime import datetime, timedelta
from outreach import ZONE, read_values, append_values
from google_preflight import file_services, verify_crm
from smtp_preflight import validate_sender
from queue_audit import address

def parse_dsn(msg, known):
    sender=address(parseaddr(str(msg.get("From","")))[1])
    if sender != "mailer-daemon@googlemail.com":
        return []
    if msg.get_content_type() != "multipart/report" or msg.get_param("report-type") != "delivery-status":
        return []
    mid=str(msg.get("Message-ID","")).strip()
    if not mid:
        return []
    try:
        stamp=parsedate_to_datetime(str(msg["Date"])).astimezone(ZONE).isoformat()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return []
    result=[]
    for part in msg.walk():
        if part.get_content_type()!="message/delivery-status":
            continue
        for block in part.get_payload():
            final=str(block.get("Final-Recipient",""))
            original=str(block.get("Original-Recipient",""))
            addr=address(final.partition(";")[2])
            if not addr or addr not in known:
                continue
            if original and address(original.partition(";")[2])!=addr:
                continue
            status=str(block.get("Status","")).strip()
            if str(block.get("Action","")).lower()!="failed" or not re.fullmatch(r"5\.\d{1,3}\.\d{1,3}",status):
                continue
            key="DSN-"+hashlib.sha256((mid+"|"+addr+"|"+status).encode()).hexdigest()[:32]
            decision="Виключити з повторного надсилання" if status=="5.1.1" else "Не повторювати до перевірки"
            reason="Скринька не існує" if status=="5.1.1" else "Постійна помилка доставки; необхідна перевірка"
            result.append([addr,known[addr],stamp,status,reason,key,decision])
    return result

def new_records(rows, existing):
    seen={(address(r[0]),str(r[5])) for r in existing if len(r)>5}
    # Existing legacy records may use Gmail IDs instead of hashed Message-ID;
    # preserve those records and suppress a duplicate address/status.
    pairs={(address(r[0]),code) for r in existing if len(r)>3
           for code in re.findall(r"\b5\.\d{1,3}\.\d{1,3}\b",str(r[3]))}
    out=[]
    for r in rows:
        key=(address(r[0]),r[5])
        pair=(address(r[0]),r[3])
        if key in seen or pair in pairs:
            continue
        seen.add(key)
        pairs.add(pair)
        out.append(r)
    return out

def known_correspondence(legacy, history):
    result={}
    for r in legacy:
        if len(r)>7 and r[7]=="Надіслано" and r[3] and r[6]:
            result[address(r[3])]=r[1]
    for r in history:
        if len(r)>7 and r[7] in {"SENT","Надіслано"} and r[3] and r[5]:
            result[address(r[3])]=r[2]
    return result

def scan_mailbox(owner, password, known):
    since=(datetime.now(ZONE)-timedelta(days=30)).strftime("%d-%b-%Y")
    result=[]
    with imaplib.IMAP4_SSL("imap.gmail.com",993,ssl_context=ssl.create_default_context(),timeout=30) as conn:
        conn.login(owner,password)
        status,_=conn.select("INBOX",readonly=True)
        if status!="OK":
            raise RuntimeError("Mailbox unavailable")
        status,data=conn.uid("SEARCH",None,"SINCE",since,"FROM",'"mailer-daemon@googlemail.com"')
        if status!="OK":
            raise RuntimeError("Search failed")
        ids=data[0].split()
        if len(ids)>100:
            raise RuntimeError("Review required: more than 100 delivery notices")
        for uid in ids:
            status,parts=conn.uid("FETCH",uid,"(BODY.PEEK[])")
            if status!="OK":
                raise RuntimeError("Fetch failed")
            payload=next((p[1] for p in parts if isinstance(p,tuple) and isinstance(p[1],bytes)),None)
            if payload is None:
                raise RuntimeError("Missing message")
            result.extend(parse_dsn(email.message_from_bytes(payload,policy=policy.default),known))
    return len(ids),result

def run(apply=False):
    owner=validate_sender(os.environ["EMAIL_ADDRESS"],os.environ["EXPECTED_GMAIL"])
    sheets,_=file_services()
    sid=os.environ["CRM_ID"]
    verify_crm(sheets,sid,owner)
    known=known_correspondence(read_values(sheets,sid,"'Контрагенти'!A2:M"),read_values(sheets,sid,"'Історія розсилок'!A2:J"))
    checked,records=scan_mailbox(owner,os.environ["EMAIL_APP_PASSWORD"],known)
    rows=new_records(records,read_values(sheets,sid,"'Повернення'!A2:G"))
    if apply and rows:
        append_values(sheets,sid,"'Повернення'!A:G",rows)
        if new_records(rows,read_values(sheets,sid,"'Повернення'!A2:G")):
            raise RuntimeError("Readback failed")
    print("MAILBOX_DSN_OK",checked,"NEW_RECORDS",len(rows),"APPLY",apply)

if __name__=="__main__":
    import sys
    try:
        run("--apply" in sys.argv)
    except Exception as exc:
        print("MAILBOX_DSN_ERROR",type(exc).__name__)
        raise SystemExit(1)
