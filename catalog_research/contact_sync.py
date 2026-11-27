"""Enrich the private working Sheet with publicly listed organization-level contacts.
No email sending, personal-contact extraction, or contact artifacts.
"""
import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import socket
import time
from urllib.parse import urljoin, urlsplit, unquote
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SID = "1vILlO0NL4MUahv7zThKMIHud9mvWd0m8p5BWFyvLu28"
TITLE = "Індивідуальні контакти"
HEADER = ["Назва організації","Профіль діяльності","Email","Телефон","Місто"]
UA = "NGOGrantsCatalog/1.0 (+https://github.com/Prool-bot/ngo-grants-outreach)"
ROLES = re.compile(r"^(info|office|contact[s]?|hello|sales|marketing|advert|ads|adv|reklama|pr|press|editor|support|order|admin|partnership[s]?|communication[s]?|reception|secretariat|service|shop|general|mail|enquiries|inquiries)([._+-][a-z0-9_-]+)?$",re.I)
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}",re.I)
EXCLUDED = re.compile(r"аграр|сільськогосподар|agricultur|agronom|військов|military",re.I)
CONTACT = re.compile(r"контакт|зв[’'ʼ]?язок|contact|kontakt|співпрац|партнерств|collaboration|partnership",re.I)
SOCIAL = ("facebook.com","instagram.com","linkedin.com","t.me","youtube.com","twitter.com","x.com")
CITIES = ["Київ","Харків","Одеса","Львів","Дніпро","Запоріжжя","Вінниця","Полтава","Чернігів","Черкаси","Суми","Житомир","Рівне","Луцьк","Тернопіль","Івано-Франківськ","Ужгород","Хмельницький","Чернівці","Кропивницький","Миколаїв","Херсон","Кременчук","Кривий Ріг","Кам'янець-Подільський","Павлоград"]
CITY_MAP = dict(zip(["Kyiv","Kharkiv","Odesa","Lviv","Dnipro","Zaporizhzhia","Vinnytsia","Poltava","Chernihiv","Cherkasy","Sumy","Zhytomyr","Rivne","Lutsk","Ternopil","Ivano-Frankivsk","Uzhhorod","Khmelnytskyi","Chernivtsi","Kropyvnytskyi","Mykolaiv","Kherson","Kremenchuk","Kryvyi Rih","Kamianets-Podilskyi","Pavlohrad"], CITIES))

def key(v):
    return re.sub(r"[^\w]+","",str(v).casefold())
def email_key(v):
    return str(v).strip().casefold()
def host(u):
    return (urlsplit(u).hostname or "").lower().removeprefix("www.")
def safe_url(u):
    try:
        p=urlsplit(u)
        if p.scheme not in ("https","http") or p.username or p.password or p.port not in (None,80,443) or not p.hostname:
            return False
        h=host(u)
        if any(h==s or h.endswith("."+s) for s in SOCIAL):
            return False
        return all(ipaddress.ip_address(x[4][0]).is_global for x in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=="https" else 80),type=socket.SOCK_STREAM))
    except (ValueError,OSError):
        return False

def fetch(session,url,base,robots=True):
    if not safe_url(url) or host(url)!=host(base):
        return None
    if robots:
        rp=RobotFileParser()
        root=urlsplit(url)
        rurl=f"{root.scheme}://{root.netloc}/robots.txt"
        rr=fetch(session,rurl,base,False)
        if rr is None:
            return None
        if rr.status_code==200:
            rp.parse(rr.text.splitlines())
            if not rp.can_fetch(UA,url):
                return None
        elif rr.status_code!=404:
            return None
    try:
        response=session.get(url,timeout=(4,7),allow_redirects=False,stream=True)
        if response.is_redirect:
            target=urljoin(url,response.headers.get("Location",""))
            response.close()
            # Follow only same-host HTTP-to-HTTPS or www redirects; never leave official domain.
            if host(target)!=host(base) or target==url or not safe_url(target):
                return None
            if robots:
                return fetch(session,target,base,False)
            return None
        if response.status_code not in (200,404):
            response.close()
            return None
        buf=bytearray()
        for chunk in response.iter_content(65536):
            buf.extend(chunk)
            if len(buf)>1500000:
                response.close()
                return None
        response._content=bytes(buf)
        response.close()
        return response
    except requests.RequestException:
        return None

def phone(v):
    if not re.fullmatch(r"[+0-9\s().-]+",str(v)):
        return ""
    d=re.sub(r"\D","",str(v))
    if len(d)==10 and d.startswith("0"):
        d="38"+d
    return "+"+d if len(d)==12 and d.startswith("380") else ""

def generic_email(v,known=""):
    v=unquote(str(v)).removeprefix("mailto:").split("?")[0].strip()
    if not EMAIL.fullmatch(v):
        return ""
    if email_key(v)==email_key(known) or ROLES.fullmatch(v.split("@")[0]):
        return v
    return ""

def structured(soup):
    def visit(obj):
        if isinstance(obj,list):
            for i in obj:
                yield from visit(i)
        elif isinstance(obj,dict):
            typ=obj.get("@type",[])
            if isinstance(typ,str):
                typ=[typ]
            if any(t in ("Organization","LocalBusiness","Store","EducationalOrganization","CollegeOrUniversity","NGO","Corporation","Library","BookStore","Museum","NewsMediaOrganization") for t in typ):
                yield obj
            if "@graph" in obj:
                yield from visit(obj["@graph"])
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            yield from visit(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError):
            continue

def extract(soup,known=""):
    emails,phones,cities=[],[],[]
    def add(seq,v):
        if v and v not in seq:
            seq.append(v)
    for obj in structured(soup):
        for v in [obj]+([obj["contactPoint"]] if isinstance(obj.get("contactPoint"),dict) else obj.get("contactPoint",[]) if isinstance(obj.get("contactPoint"),list) else []):
            if not isinstance(v,dict):
                continue
            add(emails,generic_email(v.get("email",""),known))
            add(phones,phone(v.get("telephone","")))
        addresses=obj.get("address",[])
        if isinstance(addresses,dict):
            addresses=[addresses]
        if isinstance(addresses,list):
            for a in addresses:
                if isinstance(a,dict):
                    c=str(a.get("addressLocality","")).strip()
                    if c and len(c)<80:
                        add(cities,CITY_MAP.get(c,c))
    # Only generic organizational mailboxes; office telephone links in site-wide header/footer.
    for a in soup.select("a[href^='mailto:']"):
        add(emails,generic_email(a["href"],known))
    for a in soup.select("header a[href^='tel:'], footer a[href^='tel:'], [role='banner'] a[href^='tel:'], [role='contentinfo'] a[href^='tel:']"):
        add(phones,phone(unquote(a["href"][4:])))
    # Existing role mailbox can also be visible plain text, not just a mailto link.
    for v in EMAIL.findall(soup.get_text(" ",strip=True)):
        add(emails,generic_email(v,known))
    txt=soup.get_text(" ",strip=True)
    for c in CITIES:
        if re.search(r"(?:м\.\s*|місто\s+)"+re.escape(c)+r"\b",txt,re.I):
            add(cities,c)
    return emails,phones,cities

def find_contact(session,site,known=""):
    if not site or not safe_url(site):
        return {},False
    pages=[site]
    root=urlsplit(site)
    home=f"{root.scheme}://{root.netloc}/"
    if site!=home:
        pages.append(home)
    out={}
    fetched=False
    visited=set()
    while pages and len(visited)<4:
        url=pages.pop(0)
        if url in visited:
            continue
        visited.add(url)
        response=fetch(session,url,site)
        if response is None or response.status_code!=200 or "html" not in response.headers.get("content-type","").lower():
            continue
        fetched=True
        soup=BeautifulSoup(response.content,"html.parser")
        e,p,c=extract(soup,known)
        if e and "email" not in out:
            out["email"]=(known if known and any(email_key(x)==email_key(known) for x in e) else e[0],response.url)
        if p and "phone" not in out:
            out["phone"]=("; ".join(p[:3]),response.url)
        if c and "city" not in out:
            out["city"]=("; ".join(c[:3]),response.url)
        if len(out)==3:
            break
        for a in soup.select("a[href]"):
            if CONTACT.search(a.get_text(" ",strip=True)) or CONTACT.search(a["href"]):
                u=urljoin(response.url,a["href"]).split("#")[0]
                if host(u)==host(site) and u not in visited and u not in pages and urlsplit(u).scheme in ("http","https"):
                    pages.append(u)
        time.sleep(.3)
    return out,fetched

def read(api,sid,title,ran):
    return api.values().get(spreadsheetId=sid,range=f"'{title}'!{ran}").execute().get("values",[])
def pad(row,n):
    return list(row)+[""]*max(0,n-len(row))
def cell(value,note=""):
    return {"userEnteredValue":{"stringValue":str(value)},"note":note}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=20)
    args=p.parse_args()
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    info=json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    if info.get("client_email")!="ngo-grants-outreach@ngo-grants-outreach.iam.gserviceaccount.com" or os.environ["CRM_ID"]!=SID:
        raise ValueError("Unexpected CRM destination or service account")
    creds=Credentials.from_service_account_info(info,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    api=build("sheets","v4",credentials=creds,cache_discovery=False).spreadsheets()
    meta=api.get(spreadsheetId=SID,fields="sheets(properties)").execute()
    props=next(s["properties"] for s in meta["sheets"] if s["properties"]["title"]==TITLE)
    tab=props["sheetId"]
    existing=read(api,SID,TITLE,"A1:E"+str(props["gridProperties"]["rowCount"]))
    if existing[0]!=HEADER:
        raise ValueError("Unexpected contact table headers")
    crm=read(api,SID,"Контрагенти","A1:E1000")
    if crm[0][:5]!=["ID","Організація","Сектор","Email","Раніше зазначене джерело"]:
        raise ValueError("Unexpected historical source headers")
    candidates=read(api,SID,"Кандидати","A1:F5000")
    if candidates[0][:6]!=["ID","Організація","ЄДРПОУ","Категорія","Сайт","Джерело"]:
        raise ValueError("Unexpected candidate headers")
    sources={email_key(r[3]):r[4] for row in crm[1:] if (r:=pad(row,5))[3] and r[4]}
    rows=[pad(r,5) for r in existing[1:]]
    known_names={key(r[0]) for r in rows if r[0]}
    known_emails={email_key(r[2]) for r in rows if r[2]}
    stamp=dt.datetime.now(dt.timezone.utc).date().isoformat()
    requests_out=[]
    def put(index,col,v,url):
        requests_out.append({"updateCells":{"start":{"sheetId":tab,"rowIndex":index,"columnIndex":col},"rows":[{"values":[cell(v,"Офіційне джерело: "+url+" | "+stamp)]}],"fields":"userEnteredValue,note"}})
    todo=[]
    for i,r in enumerate(rows,1):
        if not all(r[:5]) and not EXCLUDED.search(r[0]+" "+r[1]) and sources.get(email_key(r[2])):
            todo.append((i,r[0],r[1],r[2],sources[email_key(r[2])],r))
    new=[]
    for row in candidates[1:]:
        r=pad(row,6)
        if r[1] and r[3] and r[4] and key(r[1]) not in known_names and not EXCLUDED.search(r[1]+" "+r[3]):
            new.append((None,r[1],r[3].split(" — ",1)[-1], "",r[4],[""]*5))
    # Rotate incomplete records and new candidates; no contact is published to artifacts/logs.
    def rotate(seq):
        if not seq:
            return seq
        offset=(dt.date.today().toordinal()*10)%len(seq)
        return seq[offset:]+seq[:offset]
    todo=rotate(todo)[:max(1,args.limit//2)]+rotate(new)[:max(1,args.limit//2)]
    appended=[]
    checked=0
    with requests.Session() as session:
        session.headers["User-Agent"]=UA
        for i,name,profile,known,site,old in todo:
            result,fetched=find_contact(session,site,known)
            checked+=int(fetched)
            if i is not None:
                # Never replace a user's entered value.
                for col,label in [(2,"email"),(3,"phone"),(4,"city")]:
                    if not old[col] and label in result:
                        value,url=result[label]
                        if col==2 and email_key(value) in known_emails:
                            continue
                        put(i,col,value,url)
            elif all(k in result for k in ("email","phone","city")) and key(name) not in known_names and email_key(result["email"][0]) not in known_emails:
                known_names.add(key(name)); known_emails.add(email_key(result["email"][0]))
                appended.append({"values":[cell(name,"Офіційний сайт: "+site),cell(profile)]+[cell(result[k][0],"Офіційне джерело: "+result[k][1]+" | "+stamp) for k in ("email","phone","city")]})
    if appended:
        start=len(existing)
        end=start+len(appended)
        if end>props["gridProperties"]["rowCount"]:
            requests_out.insert(0,{"appendDimension":{"sheetId":tab,"dimension":"ROWS","length":max(100,len(appended))}})
        requests_out.append({"updateCells":{"start":{"sheetId":tab,"rowIndex":start,"columnIndex":0},"rows":appended,"fields":"userEnteredValue,note"}})
        requests_out.append({"setBasicFilter":{"filter":{"range":{"sheetId":tab,"startRowIndex":0,"endRowIndex":end,"startColumnIndex":0,"endColumnIndex":5}}}})
    if requests_out:
        # Guard against changes made while researching. No stale-row writes.
        if read(api,SID,TITLE,"A1:E"+str(props["gridProperties"]["rowCount"]))!=existing:
            raise RuntimeError("Contact table changed during research; retry next run")
        api.batchUpdate(spreadsheetId=SID,body={"requests":requests_out}).execute()
    final=read(api,SID,TITLE,"A1:E"+str(max(props["gridProperties"]["rowCount"],len(existing)+len(appended))))
    if final[0]!=HEADER or len(final)<len(existing)+len(appended):
        raise RuntimeError("Readback failed")
    print("CONTACT_CATALOG", "attempted",len(todo),"sites_accessed",checked,"updated_cells",sum("updateCells" in r for r in requests_out)-bool(appended),"new_complete",len(appended),"total_rows",len(final)-1,"complete",sum(all(pad(r,5)[:5]) for r in final[1:]),flush=True)
if __name__=="__main__":
    main()
