"""Daily operational report to the verified owner mailbox only."""
import os, smtplib, ssl
from collections import Counter
from datetime import datetime
from email.message import EmailMessage
from outreach import ZONE, read_values, append_values
from google_preflight import file_services, verify_crm
from smtp_preflight import validate_sender
from procurement_quality import triage

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

def cycle_coverage(journal, now, first_day="2026-11-30"):
    day=now.date().isoformat()
    if day < first_day:
        return 0,0,0,0
    expected={f"{day}T{h:02d}:00{now.strftime('%z')}" for h in range(9,18)
              if now.weekday()<5 and (h<now.hour or (h==now.hour and now.minute>=15))}
    states={r[0]:r[5] for r in journal if len(r)>=6 and r[4]=="DISCOVERY" and r[0] in expected}
    return len(expected),len(states),len(expected-set(states)),sum(x=="OK" for x in states.values())

def run(send=False, self_test=False):
    now=datetime.now(ZONE)
    day=now.date().isoformat()
    address=validate_sender(os.environ["EMAIL_ADDRESS"],os.environ["EXPECTED_GMAIL"])
    sheets,_=file_services()
    sid=os.environ["CRM_ID"]
    verify_crm(sheets,sid,address)
    journal=read_values(sheets,sid,"'Системний журнал'!A2:J")
    n, statuses, discoveries=summarize(journal,day)
    planned, executed, missing, successful=cycle_coverage(journal,now)
    opportunities=read_values(sheets,sid,"'Закупівлі'!A2:K")
    organizations=read_values(sheets,sid,"'Кандидати'!A2:K")
    quality=Counter(triage(r[3],r[5],r[7],now.date())[0] for r in opportunities if len(r)>=8)
    categories=Counter(str(r[3]).split(" — ",1)[0] for r in organizations if len(r)>3)
    queue=read_values(sheets,sid,"'Черга'!A2:K")
    returns=read_values(sheets,sid,"'Повернення'!A2:G")
    invalid=read_values(sheets,sid,"'Недійсні'!A2:F")
    history=read_values(sheets,sid,"'Історія розсилок'!A2:J")
    excluded=len({str(r[0]).strip().casefold() for r in invalid if r and r[0]})
    today_history=sum(1 for r in history if len(r)>6 and str(r[6]).startswith(day))
    body=(f"NGO Grants Outreach — {day}\n"
          f"Циклів: {n}; успішних: {statuses['OK']}; часткових: {statuses['PARTIAL']}; помилок: {statuses['ERROR']}\n"
          f"Планових циклів: {planned}; відмічено у журналі: {executed}; успішних: {successful}; без запису: {missing}\n"
          f"Нових записів за журналом (включно з пілотами): {discoveries}\n"
          f"Закупівель у реєстрі: {len(opportunities)}\n"
          f"Організацій для дослідження: {len(organizations)}\n"
          f"Категорій організацій з записами: {len(categories)}\n"
          f"Записів у черзі звернень: {len(queue)}\n"
          f"Операцій у журналі розсилок за день: {today_history}\n"
          f"Повернень у реєстрі (накопичено): {len(returns)}\n"
          f"Підтверджених недійсних адрес у реєстрі: {excluded}\n"
          "Автоматичне читання нових повернень із Gmail не підключено; показники відображають лише наявний реєстр.\n"
          "Якість закупівель (автоматична попередня оцінка): "+", ".join(f"{k}: {v}" for k,v in sorted(quality.items()))+"\n"
          "Зовнішня розсилка не активована. Результати потребують перевірки.\n")
    if not send and not self_test:
        print("REPORT_PREVIEW_OK",n,discoveries,len(opportunities),len(organizations))
        print("PROCUREMENT_QUALITY",dict(quality))
        print("CATEGORY_COVERAGE",len(categories),"QUEUE_ROWS",len(queue))
        print("SCHEDULE_COVERAGE",planned,executed,missing,successful)
        print("DELIVERY_REPORT",len(returns),excluded,"HISTORY_TODAY",today_history,"GMAIL_SYNC_NOT_ACTIVE")
        return
    if not self_test and (now.weekday()>=5 or now.hour!=17 or now.minute<30):
        print("REPORT_SKIPPED_OUTSIDE_WINDOW")
        return
    key=("REPORT-SELF-TEST-" if self_test else "REPORT-")+day
    if any(r and r[0]==key for r in journal):
        print("REPORT_SKIPPED_ALREADY_ATTEMPTED")
        return
    stamp=now.isoformat(timespec="seconds")
    # Fail closed after uncertain delivery; never automatically send duplicates.
    append_values(sheets,sid,"'Системний журнал'!A:J",[[key,stamp,stamp,"","REPORT","ATTEMPTED",0,0,"",""]])
    msg=EmailMessage()
    msg["From"]=address
    msg["To"]=address
    msg["Subject"]="NGO Grants Outreach — "+("тест звіту " if self_test else "щоденний звіт ")+day
    msg.set_content(("Технічний тест. Отримувач — лише власник.\n\n" if self_test else "")+body)
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
        run("--send" in sys.argv, "--self-test" in sys.argv)
    except Exception as e:
        print("REPORT_ERROR",type(e).__name__)
        raise SystemExit(1)
