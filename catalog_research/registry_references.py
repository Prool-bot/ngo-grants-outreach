"""Independent scholarly registry references; no contacts or organization website extraction."""
import re
import requests
from catalog_research.run import EXCLUDED, HEADERS

ROR="https://api.ror.org/v2/organizations"
CROSSREF="https://api.crossref.org/funders"
ROR_SPECS=[
    ("EDU-01","education","university",r"universit|університет"),
    ("EDU-07","facility","research institute",r"research|institute|інститут|науков"),
    ("NGO-12","funder","foundation",r"fund|foundation|фонд"),
]

def reference(identifier,title,code):
    if not title or EXCLUDED.search(title):
        return None
    if re.fullmatch(r"Q[1-9]\d*",identifier):
        url="https://www.wikidata.org/wiki/"+identifier
    elif re.fullmatch(r"ROR:0[0-9a-z]{8}",identifier):
        url="https://ror.org/"+identifier.split(":",1)[1]
    elif re.fullmatch(r"CROSSREF:10\.13039/\d+",identifier):
        url="https://doi.org/"+identifier.split(":",1)[1]
    else:
        return None
    return {"source_id":identifier,"title":title,"source_url":url,
            "category_codes":[code],"status":"REFERENCE_REVIEW_REQUIRED"}

def parse_ror(item,code,kind,pattern):
    if item.get("status")!="active" or kind not in item.get("types",[]):
        return None
    if not any(x.get("geonames_details",{}).get("country_code")=="UA" for x in item.get("locations",[])):
        return None
    rid=str(item.get("id","")).removeprefix("https://ror.org/")
    if not re.fullmatch(r"0[0-9a-z]{8}",rid):
        return None
    names=item.get("names",[])
    title=next((n.get("value","") for n in names if n.get("lang")=="uk" and "label" in n.get("types",[])),"")
    title=title or next((n.get("value","") for n in names if "ror_display" in n.get("types",[])),"")
    all_names=" ".join(str(n.get("value","")) for n in names)
    if not re.search(pattern,all_names,re.I) or EXCLUDED.search(all_names):
        return None
    qids=[v for x in item.get("external_ids",[]) if str(x.get("type","")).lower()=="wikidata"
          for v in x.get("all",[]) if re.fullmatch(r"Q[1-9]\d*",str(v))]
    row=reference(qids[0] if len(set(qids))==1 else "ROR:"+rid,title,code)
    if row:
        row["sources"]=["ROR"]
    return row

def parse_crossref(item):
    if str(item.get("location","")).strip().casefold() not in {"ukraine","україна"}:
        return None
    identifier=str(item.get("id",""))
    if identifier.isdigit():
        identifier="10.13039/"+identifier
    title=str(item.get("name","")).strip()
    row=reference("CROSSREF:"+identifier,title,"NGO-12")
    if row:
        row["sources"]=["Crossref"]
    return row

def get_json(session,url,params):
    r=session.get(url,params=params,headers=HEADERS,timeout=(8,20))
    r.raise_for_status()
    return r.json()

def collect(offset):
    refs=[]
    stats=[]
    with requests.Session() as s:
        for code,kind,query,pattern in ROR_SPECS:
            try:
                data=get_json(s,ROR,{"query":query,"filter":f"locations.geonames_details.country_code:UA,types:{kind}",
                    "page":1+offset//20})
                items=data["items"]
                rows=[r for item in items if (r:=parse_ror(item,code,kind,pattern))]
                refs.extend(rows)
                stats.append({"source":"ROR","code":code,"status":"OK","found":len(rows)})
            except Exception as e:
                stats.append({"source":"ROR","code":code,"status":"ERROR","error":type(e).__name__,"found":0})
                break
        try:
            data=get_json(s,CROSSREF,{"query":"Ukraine","rows":20,"offset":offset})
            rows=[r for item in data["message"]["items"] if (r:=parse_crossref(item))]
            refs.extend(rows)
            stats.append({"source":"Crossref","code":"NGO-12","status":"OK","found":len(rows)})
        except Exception as e:
            stats.append({"source":"Crossref","code":"NGO-12","status":"ERROR","error":type(e).__name__,"found":0})
    return refs,stats
