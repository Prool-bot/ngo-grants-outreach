"""Daily operational report to the verified owner mailbox only."""
import os, smtplib, ssl
from collections import Counter
from datetime import datetime
from email.message import EmailMessage
from outreach import ZONE, read_values, append_values
from google_preflight import file_services, verify_crm
from smtp_preflight import validate_sender

def summarize(journal, day):
    cycles = {}
    for r in journal:
        if len(r)<8 or not r[1].startswith(day) or r[4] not in {"DISCOVERY","PILOT"}:
            continue
        cycles[r[0]]=r
    statuses=Counter(r[5] for r in cycles.values())
    # Retries can add distinct records before a subsequent successful attempt.
    discoveries = sum(int(r[6] or 0) for r in journal if len(r)>=8 and r[1].startswith(day) and r[4] in {"DISCOVERY","PILOT"})
    return len(cycles), statuses, discoveries

def run(send=False):
    now=datetime.now(ZONE)
    day=now.date().isoformat()
    address=validate_sender(os.environ["EMAIL_ADDRESS"],os.environ["EXPECTED_GMAIL"])
    sheets,_=file_services()
    sid=os.environ["CRM_ID"]
    verify_crm(sheets,sid,address)
    journal=read_values(sheets,sid,"'Системний журнал'!A2:J")
    n, statuses, discoveries=summarize(journal,day)
    opportunities=read_values(sheets,sid,"'Закупівлі'!A2:K")
    organizations=read_values(sheets,sid,"'Кандидати'!A2:K")
    body=(f"NGO Grants Outreach — {day}\n"
          f"Циклів: {n}; успішних: {statuses['OK']}; часткових: {statuses['PARTIAL']}; помилок: {statuses['ERROR']}\n"
          f"Нових записів за журналом: {discoveries}\n"
          f"Закупівель у реєстрі: {len(opportunities)}\n"
          f"Організацій для дослідження: {len(organizations)}\n"
          "Зовнішня розсилка не активована. Результати потребують перевірки.\n")
    if not send:
        print("REPORT_PREVIEW_OK",n,discoveries,len(opportunities),len(organizations))
        return
    if now.weekday()>=5 or now.hour!=17 or now.minute<30:
        print("REPORT_SKIPPED_OUTSIDE_WINDOW")
        return
    key="REPORT-"+day
    if any(r and r[0]==key for r in journal):
        print("REPORT_SKIPPED_ALREADY_ATTEMPTED")
        return
    stamp=now.isoformat(timespec="seconds")
    # Fail closed after uncertain delivery; never automatically send duplicates.
    append_values(sheets,sid,"'Системний журнал'!A:J",[[key,stamp,stamp,"","REPORT","ATTEMPTED",0,0,"",""]])
    msg=EmailMessage()
    msg["From"]=address
    msg["To"]=address
    msg["Subject"]="NGO Grants Outreach — щоденний звіт "+day
    msg.set_content(body)
    with smtplib.SMTP("smtp.gmail.com",587,timeout=30) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(address,os.environ["EMAIL_APP_PASSWORD"])
        if server.send_message(msg,from_addr=address,to_addrs=[address]):
            raise RuntimeError("Owner report rejected")
    append_values(sheets,sid,"'Системний журнал'!A:J",[[key+"-DONE",stamp,stamp,datetime.now(ZONE).isoformat(timespec="seconds"),"REPORT","OK",0,0,"",""]])
    print("OWNER_REPORT_ACCEPTED")

if __name__=="__main__":
    import sys
    try:
        run("--send" in sys.argv)
    except Exception as e:
        print("REPORT_ERROR",type(e).__name__)
        raise SystemExit(1)
