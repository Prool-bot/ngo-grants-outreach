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
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit, unquote
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SID = "1vILlO0NL4MUahv7zThKMIHud9mvWd0m8p5BWFyvLu28"
TITLE = "Індивідуальні контакти"
HEADER = ["Назва організації","Профіль діяльності","Email","Телефон","Місто","Код категорії","Категорія","Короткий опис діяльності","Статус контакту","Сайт / офіційна сторінка"]
UA = "NGOGrantsCatalog/1.0 (+https://github.com/Prool-bot/ngo-grants-outreach)"
ROLES = re.compile(r"^(info|office|contact[s]?|hello|sales|marketing|advert|advertising|ads|adv|reklama|pr|press|editor|editorial|support|order[s]?|admin|partnership[s]?|partner[s]?|communication[s]?|reception|secretariat|service|shop|general|mail|enquiries|inquiries|rektorat|rectorate|kanz|kanc|kanzeliaria|chancellery|admission[s]?|customer[._-]?service)(?:[._-](?:ua|ukraine|kyiv|lviv|kharkiv|odesa|dnipro|team))?$",re.I)
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}",re.I)
EXCLUDED = re.compile(r"аграр|сільськогосподар|agricultur|agronom|ветеринар|рослинництв|plant variety|природокористування|військов|military|\.mil\.gov\.ua",re.I)
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

def fetch(session,url,base,robots=True,redirects=1):
    if not safe_url(url) or host(url)!=host(base):
        return None
    if robots:
        rp=RobotFileParser()
        root=urlsplit(url)
        rurl=f"{root.scheme}://{root.netloc}/robots.txt"
        cache=getattr(session,"_catalog_robots",{})
        session._catalog_robots=cache
        if rurl not in cache:
            rr=fetch(session,rurl,base,False)
            if rr is None or rr.status_code not in (200,404):
                cache[rurl]=False
            elif rr.status_code==404:
                cache[rurl]=True
            else:
                rp.parse(rr.text.splitlines())
                cache[rurl]=rp
        policy=cache[rurl]
        if policy is False or (policy is not True and not policy.can_fetch(UA,url)):
            return None
    try:
        response=session.get(url,timeout=(4,7),allow_redirects=False,stream=True)
        if response.is_redirect:
            target=urljoin(url,response.headers.get("Location",""))
            response.close()
            # Follow only same-host HTTP-to-HTTPS or www redirects; never leave official domain.
            if host(target)!=host(base) or target==url or not safe_url(target):
                return None
            if redirects:
                return fetch(session,target,base,robots,redirects-1)
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

def extract(soup,known="",contact_page=False):
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
    # A number explicitly labelled as a general office or call-centre channel.
    for a in soup.select("a[href^='tel:']"):
        context=a.parent.get_text(" ",strip=True) if a.parent else ""
        if len(context)<160 and re.search(r"кол[- ]?центр|гаряч[аої] ліні|приймальн|телефон офіс|відділ продаж|call.cent[er]+|reception|office phone|general enquiries",context,re.I):
            add(phones,phone(unquote(a["href"][4:])))
    # Explicit organizational contact labels on official contact pages, not unlabeled personal numbers.
    if contact_page:
        org_label=re.compile(r"^(?:телефон(?:и)?(?:\s+(?:офісу|приймальні|магазину|відділу продажу))?|тел\.?|phone|telephone|контактн(?:ий|і)\s+телефон(?:и)?|кол[- ]?центр|call\s*cent(?:er|re)|приймальня|рецепція|відділ продажу|загальні контакти|офіс)\s*[:：]?\s*$",re.I)
        number_pattern=re.compile(r"(?<!\d)(?:\+?38[\s().-]*)?0(?:[\s().-]*\d){9}(?!\d)")
        for tag in soup.find_all(["p","li","div","td","dt","dd","span","strong","b","label"]):
            if tag.find(["p","li","div","td","dt","dd"]):
                continue
            txt=tag.get_text(" ",strip=True)
            if len(txt)>120:
                continue
            m=re.match(r"^([^:：]{2,45})[:：]\s*(.+)$",txt)
            if m and org_label.fullmatch(m.group(1).strip()):
                for val in number_pattern.findall(m.group(2)):
                    add(phones,phone(val))
            elif org_label.fullmatch(txt):
                sibling=tag.find_next_sibling()
                if sibling:
                    value=sibling.get_text(" ",strip=True)
                    if len(value)<100 and re.fullmatch(r"[+0-9\s().,;/-]+",value):
                        for val in number_pattern.findall(value):
                            add(phones,phone(val))
    # Existing role mailbox can also be visible plain text, not just a mailto link.
    for v in EMAIL.findall(soup.get_text(" ",strip=True)):
        add(emails,generic_email(v,known))
    txt=soup.get_text(" ",strip=True)
    for c in CITIES:
        if re.search(r"(?:м\.\s*|місто\s+)"+re.escape(c)+r"\b",txt,re.I):
            add(cities,c)
    return emails,phones,cities

def site_description(soup):
    for selector in ('meta[property="og:description"]','meta[name="description"]'):
        node=soup.select_one(selector)
        if not node:
            continue
        value=re.sub(r"\s+"," ",str(node.get("content",""))).strip()
        if not re.search(r"[а-яіїєґ]",value,re.I) or re.search(r"cookie|файли cookie|купити|знижк|доставк|підписуйт|увійти",value,re.I):
            continue
        first=re.split(r"(?<=[.!?])\s+",value,maxsplit=1)[0].strip()
        if 25<=len(first)<=210:
            return first.rstrip(".!?")+"."
    return ""

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
    while pages and len(visited)<6:
        url=pages.pop(0)
        if url in visited:
            continue
        visited.add(url)
        response=fetch(session,url,site)
        if response is None or response.status_code!=200 or "html" not in response.headers.get("content-type","").lower():
            continue
        fetched=True
        soup=BeautifulSoup(response.content,"html.parser")
        e,p,c=extract(soup,known,contact_page=bool(CONTACT.search(urlsplit(response.url).path)))
        description=site_description(soup)
        if description and "description" not in out:
            out["description"]=(description,response.url)
        if e and "email" not in out:
            out["email"]=(known if known and any(email_key(x)==email_key(known) for x in e) else e[0],response.url)
        if p and "phone" not in out:
            out["phone"]=("; ".join(p[:3]),response.url)
        if c and "city" not in out:
            out["city"]=("; ".join(c[:3]),response.url)
        if all(k in out for k in ("email","phone")) and (("city" in out and "description" in out) or len(visited)>=3):
            break
        for a in soup.select("a[href]"):
            if CONTACT.search(a.get_text(" ",strip=True)) or CONTACT.search(a["href"]):
                u=urljoin(response.url,a["href"]).split("#")[0]
                if host(u)==host(site) and u not in visited and u not in pages and urlsplit(u).scheme in ("http","https"):
                    pages.insert(0,u) if CONTACT.search(urlsplit(u).path) else pages.append(u)
        time.sleep(.3)
    return out,fetched

# Curated official entry points, independently checked as public organization sites.
# Contacts themselves are obtained only from the official site by find_contact.
SEEDS=[
    ("АЗУР","ART-01","https://azur.com.ua/kontakty-ua"),
    ("Akvarel","ART-01","https://akvarel.com/krivii-rig/about"),
    ("Raphael","ART-01","https://raph.com.ua/"),
    ("Видавництво Старого Лева","ART-10","https://starylev.com.ua/contact"),
    ("Наш Формат","ART-10","https://nashformat.ua/contacts"),
    ("Ранок","ART-10","https://www.ranok.com.ua/"),
    ("Мистецький арсенал","ART-07","https://artarsenal.in.ua/kontakty/"),
    ("Києво-Могилянська бізнес-школа","EDU-04","https://kmbs.ua/ua/contacts"),
    ("Центр демократії та верховенства права","NGO-10","https://cedem.org.ua/who-we-are/contacts/"),
    ("ПУМБ","FIN-01","https://about.pumb.ua/info"),
    ("Райффайзен Банк","FIN-01","https://raiffeisen.ua/kontakty"),
    ("SoftServe Business Systems","MED-11","https://softservebs.com/ua/contact-us/"),
    ("Sigma Software","MED-11","https://sigma.software/about/our-offices-and-contacts?country=Ukraine"),
]

def rotate(seq, offset):
    return seq[offset%len(seq):]+seq[:offset%len(seq)] if seq else []

def balanced(items, day):
    groups=defaultdict(deque)
    for item in items:
        groups[item[2]].append(item)
    keys=rotate(sorted(groups),day)
    result=[]
    while keys:
        for k in keys:
            result.append(groups[k].popleft())
        keys=[k for k in keys if groups[k]]
    return result

def canonical_profile(name, profile, labels):
    profile=profile.split(" — ",1)[-1].strip()
    if profile=="Університети" and re.search(r"\bколедж\b",name,re.I):
        profile="Коледжі"
    return profile if profile in labels else ""

def reference_candidates(api,meta,session,known_names,limit,labels,day):
    from catalog_research.run import load_categories, search_category
    props=next((s["properties"] for s in meta["sheets"] if s["properties"]["title"]=="Каталог організацій"),None)
    refs=[]
    if props:
        data=api.get(spreadsheetId=SID,ranges=[f"'Каталог організацій'!A1:C{props['gridProperties']['rowCount']}"],fields="sheets(data(rowData(values(formattedValue,note))) )".replace(" ","")).execute()
        for row in data["sheets"][0].get("data",[{}])[0].get("rowData",[])[1:]:
            cells=row.get("values",[])
            if len(cells)<2:
                continue
            name=cells[0].get("formattedValue","")
            profile=canonical_profile(name,cells[1].get("formattedValue",""),labels)
            match=re.search(r"\bQ[1-9][0-9]*\b",cells[0].get("note",""))
            if match and profile and name and key(name) not in known_names and not EXCLUDED.search(name+" "+profile):
                refs.append((match.group(0),name,profile))
    # Independent rotating discovery across ALL 115 categories, even if the reference sheet is stale.
    cats=load_categories()
    catgroups=defaultdict(list)
    for cat in cats:
        catgroups[cat["group"]].append(cat)
    queried=0
    for g,items in catgroups.items():
        for cat in rotate(items,day*2)[:2]:
            try:
                _,found=search_category(session,cat,offset=((day//max(1,len(items)//2))%5)*10)
                queried+=1
                refs.extend((r["source_id"],r["title"],r["category"]) for r in found if key(r["title"]) not in known_names and not EXCLUDED.search(r["title"]+" "+r["category"]))
            except (requests.RequestException,RuntimeError,ValueError):
                break
            time.sleep(.3)
    seen=set()
    refs=[r for r in refs if not (r[0] in seen or seen.add(r[0])) and r[1].casefold()!=r[2].casefold()]
    # Rotate the source pool and use Wikidata's documented 50-entity maximum per request.
    refs=rotate(refs,day*max(1,limit))[:max(50,limit*3)]
    def claims(e,p):
        return [s.get("mainsnak",{}).get("datavalue",{}).get("value") for s in e.get("claims",{}).get(p,[]) if s.get("rank")!="deprecated"]
    result=[]
    for start in range(0,len(refs),50):
        batch=refs[start:start+50]
        try:
            response=session.get("https://www.wikidata.org/w/api.php",params={"action":"wbgetentities","ids":"|".join(r[0] for r in batch),"props":"claims","format":"json"},timeout=(5,15))
            if response.status_code in (429,503):
                break
            response.raise_for_status()
            entities=response.json().get("entities",{})
        except (requests.RequestException,ValueError):
            continue
        for qid,name,profile in batch:
            e=entities.get(qid,{})
            if any(isinstance(v,dict) and v.get("id")=="Q5" for v in claims(e,"P31")):
                continue
            ua=any(isinstance(v,dict) and v.get("id")=="Q212" for v in claims(e,"P17"))
            for site in claims(e,"P856"):
                if isinstance(site,str) and (ua or host(site).endswith(".ua")) and not EXCLUDED.search(site) and safe_url(site):
                    result.append((None,name,profile,"",site,[""]*10))
                    break
        time.sleep(.25)
    return result,queried,len(refs)

def eligible_new(result):
    # City is optional; an actual organizational phone and mailbox are mandatory.
    return all(result.get(k,("",))[0] for k in ("email","phone"))

def discover_one(item):
    i,name,profile,known,site,old=item
    with requests.Session() as session:
        session.headers["User-Agent"]=UA
        result,fetched=find_contact(session,site,known)
    return item,result,fetched

def read(api,sid,title,ran):
    return api.values().get(spreadsheetId=sid,range=f"'{title}'!{ran}").execute().get("values",[])
def pad(row,n):
    return list(row)+[""]*max(0,n-len(row))
def cell(value,note=""):
    return {"userEnteredValue":{"stringValue":str(value)},"note":note}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=100,help="New candidate research budget, not an acceptance cap")
    p.add_argument("--enrich-limit",type=int,default=20)
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
    existing=read(api,SID,TITLE,"A1:J"+str(props["gridProperties"]["rowCount"]))
    if existing[0]!=HEADER:
        raise ValueError("Unexpected contact table headers")
    from catalog_research.run import load_categories
    labels={x["label"]:x["code"] for x in load_categories()}
    crm=read(api,SID,"Контрагенти","A1:E1000")
    if crm[0][:5]!=["ID","Організація","Сектор","Email","Раніше зазначене джерело"]:
        raise ValueError("Unexpected historical source headers")
    candidate_props=next(s["properties"] for s in meta["sheets"] if s["properties"]["title"]=="Кандидати")
    candidates=read(api,SID,"Кандидати","A1:F"+str(candidate_props["gridProperties"]["rowCount"]))
    if candidates[0][:6]!=["ID","Організація","ЄДРПОУ","Категорія","Сайт","Джерело"]:
        raise ValueError("Unexpected candidate headers")
    sources={email_key(r[3]):r[4] for row in crm[1:] if (r:=pad(row,5))[3] and r[4]}
    rows=[pad(r,10) for r in existing[1:]]
    known_names={key(r[0]) for r in rows if r[0]}
    known_emails={email_key(r[2]) for r in rows if r[2]}
    known_hosts={host(r[9]) for r in rows if r[9]}
    day=dt.date.today().toordinal()
    categories_by_code={v:k for k,v in labels.items()}
    stamp=dt.datetime.now(dt.timezone.utc).date().isoformat()
    requests_out=[]
    def put(index,col,v,url):
        requests_out.append({"updateCells":{"start":{"sheetId":tab,"rowIndex":index,"columnIndex":col},"rows":[{"values":[cell(v,"Офіційне джерело: "+url+" | "+stamp)]}],"fields":"userEnteredValue,note"}})
    todo=[]
    for i,r in enumerate(rows,1):
        if (not all(r[:5]) or not r[9]) and not EXCLUDED.search(r[0]+" "+r[1]):
            site=r[9] or sources.get(email_key(r[2]),"")
            if site and site.startswith(("https://","http://")):
                todo.append((i,r[0],r[1],r[2],site,r))
    new=[]
    for row in candidates[1:]:
        r=pad(row,6)
        profile=canonical_profile(r[1],r[3],labels)
        if r[1] and profile and r[4] and key(r[1]) not in known_names and not EXCLUDED.search(r[1]+" "+r[3]+" "+r[4]):
            new.append((None,r[1],profile,"",r[4],[""]*10))
    seeds=[(None,name,categories_by_code[code],"",site,[""]*10) for name,code,site in SEEDS if code in categories_by_code]
    with requests.Session() as ref_session:
        ref_session.headers["User-Agent"]=UA
        refs,queried,refs_considered=reference_candidates(api,meta,ref_session,known_names,args.limit,labels,day)
    # New discovery has its own budget; it cannot be consumed by existing records.
    pool=seeds+balanced(rotate(refs,day)+rotate(new,day),day)
    seen_names=set(known_names)
    seen_hosts=set(known_hosts)
    discovery=[]
    for item in pool:
        _,name,profile,_,site,_=item
        h=host(site)
        if not h or h in seen_hosts or key(name) in seen_names or not profile or EXCLUDED.search(name+" "+profile+" "+site):
            continue
        if not site.startswith(("https://","http://")):
            continue
        seen_names.add(key(name));seen_hosts.add(h)
        discovery.append(item)
    todo=rotate(todo,day*max(1,args.enrich_limit))[:args.enrich_limit]
    discovery=discovery[:args.limit]
    # Parallelism across distinct organizations, each with its own session and per-site robots cache.
    work=discovery+todo
    appended=[]
    checked=0
    counts=Counter()
    accepted_categories=Counter()
    changed_rows=set()
    phones_added=0
    new_with_city=0
    with ThreadPoolExecutor(max_workers=6) as executor:
        for item,result,fetched in executor.map(discover_one,work):
            i,name,profile,known,site,old=item
            checked+=int(fetched)
            if i is not None:
                counts["enrich_accessed"]+=int(fetched)
                if known and not (email_key(result.get("email",("",""))[0])==email_key(known) or host(site)==known.split("@")[-1].lower().removeprefix("www.")):
                    counts["enrich_identity_unconfirmed"]+=1
                    continue
                if not old[9] and fetched:
                    put(i,9,site,site);changed_rows.add(i)
                for col,label in [(2,"email"),(3,"phone"),(4,"city")]:
                    if not old[col] and label in result:
                        value,url=result[label]
                        if col==2 and email_key(value) in known_emails:
                            continue
                        put(i,col,value,url);changed_rows.add(i)
                        if col==3:
                            phones_added+=1
                        if col==2:
                            known_emails.add(email_key(value))
                continue
            counts["new_accessed"]+=int(fetched)
            if not fetched:
                counts["site_unavailable_or_disallowed"]+=1
                continue
            if not result.get("email"):
                counts["missing_org_email"]+=1
            if not result.get("phone"):
                counts["missing_org_phone"]+=1
            if not eligible_new(result):
                continue
            if profile not in labels:
                counts["unclassified"]+=1
                continue
            if key(name) in known_names or email_key(result["email"][0]) in known_emails or host(site) in known_hosts:
                counts["duplicate"]+=1
                continue
            known_names.add(key(name));known_emails.add(email_key(result["email"][0]));known_hosts.add(host(site))
            description,desc_url=result.get("description",(f"Організація напряму «{profile}»; спеціалізація потребує уточнення.",""))
            desc_note=("Опис з офіційного сайту: "+desc_url+" | "+stamp) if desc_url else "Попередній опис за класифікатором; уточнити профіль."
            city,city_url=result.get("city",("",""))
            new_with_city+=bool(city)
            accepted_categories[labels[profile]]+=1
            appended.append({"values":[cell(name,"Офіційний сайт: "+site),cell(profile)]+[cell(result[k][0],"Офіційне джерело: "+result[k][1]+" | "+stamp) for k in ("email","phone")]+[cell(city,("Офіційне джерело: "+city_url+" | "+stamp) if city else "Місто не підтверджено; необов'язкове поле."),cell(labels[profile],"Попередня класифікація"),cell(profile),cell(description,desc_note),cell("Не телефонували","Ручний статус; згода не встановлена."),cell(site,"Офіційний сайт, використаний для пошуку | "+stamp)]})
    if appended:
        start=len(existing)
        end=start+len(appended)
        if end>props["gridProperties"]["rowCount"]:
            requests_out.insert(0,{"appendDimension":{"sheetId":tab,"dimension":"ROWS","length":max(100,len(appended))}})
        requests_out.append({"updateCells":{"start":{"sheetId":tab,"rowIndex":start,"columnIndex":0},"rows":appended,"fields":"userEnteredValue,note"}})
        requests_out.append({"setDataValidation":{"range":{"sheetId":tab,"startRowIndex":start,"endRowIndex":end,"startColumnIndex":8,"endColumnIndex":9},"rule":{"condition":{"type":"ONE_OF_LIST","values":[{"userEnteredValue":v} for v in ["Не визначено","Не телефонували","Не відповідають","Передзвонити","Згоду отримано","Пропозицію надіслано","Зацікавлені","Відмовилися","Співпрацюємо"]]},"strict":True,"showCustomUi":True}}})
        requests_out.append({"setBasicFilter":{"filter":{"range":{"sheetId":tab,"startRowIndex":0,"endRowIndex":end,"startColumnIndex":0,"endColumnIndex":10}}}})
    if len(existing)+len(appended)>1:
        requests_out.append({"sortRange":{"range":{"sheetId":tab,"startRowIndex":1,"endRowIndex":len(existing)+len(appended),"startColumnIndex":0,"endColumnIndex":10},"sortSpecs":[{"dimensionIndex":5,"sortOrder":"ASCENDING"},{"dimensionIndex":0,"sortOrder":"ASCENDING"}]}})
    if requests_out:
        # Guard against changes made while researching. No stale-row writes.
        if read(api,SID,TITLE,"A1:J"+str(props["gridProperties"]["rowCount"]))!=existing:
            raise RuntimeError("Contact table changed during research; retry next run")
        api.batchUpdate(spreadsheetId=SID,body={"requests":requests_out}).execute()
    final=read(api,SID,TITLE,"A1:J"+str(max(props["gridProperties"]["rowCount"],len(existing)+len(appended))))
    if final[0]!=HEADER or len(final)<len(existing)+len(appended):
        raise RuntimeError("Readback failed")
    metrics={"attempted":len(work),"sites_accessed":checked,"updated_cells":sum("updateCells" in r for r in requests_out)-bool(appended),"new_added":len(appended),"new_complete":new_with_city,"total_rows":len(final)-1,"complete":sum(all(pad(r,5)[:5]) for r in final[1:]),"new_attempted":len(discovery),"enrich_attempted":len(todo),"enriched_records":len(changed_rows),"existing_phones_added":phones_added,"new_phones_added":len(appended),"candidate_pool":len(pool),"discovery_categories_queried":queried,"reference_entities_considered":refs_considered}
    print("CONTACT_CATALOG",*(str(k)+" "+str(v) for k,v in metrics.items()),flush=True)
    print("CONTACT_CATALOG_REASONS",json.dumps(dict(counts),ensure_ascii=False,sort_keys=True),flush=True)
    print("CONTACT_CATALOG_CATEGORIES",json.dumps(dict(accepted_categories),sort_keys=True),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as summary:
            summary.write("## Contact catalog\n\n| Metric | Count |\n|---|---:|\n")
            for k,v in metrics.items():
                summary.write(f"| {k} | {v} |\n")
            summary.write("\nRejection / access counts (may overlap): "+json.dumps(dict(counts),sort_keys=True)+"\n\nNew records by category: "+json.dumps(dict(accepted_categories),sort_keys=True)+"\n")
if __name__=="__main__":
    main()
