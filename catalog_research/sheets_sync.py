"""Publish a read-only-in-purpose organization reference view to Sheets.
No mail, contact discovery, or join with the manual contact register.
"""
import argparse
import json
import os
from pathlib import Path
from catalog_research.run import load_categories

TITLE="Каталог організацій"
HEADER=["Назва організації","Профіль діяльності","Місто"]
MARKER="NGO Grants: автоматична довідкова вкладка (sheets_sync v1)"
SID="1vILlO0NL4MUahv7zThKMIHud9mvWd0m8p5BWFyvLu28"

def profile_rows(snapshot):
    labels={c["code"]:c["label"] for c in load_categories()}
    seen=set()
    rows=[]
    for item in snapshot["references"]:
        identifier=item["source_id"]
        if identifier in seen:
            raise ValueError("Duplicate source identifier")
        seen.add(identifier)
        name=str(item["title"]).strip()
        profile="; ".join(labels[c] for c in item["category_codes"] if c in labels)
        city="; ".join(item.get("cities",[]))
        if not name or not profile:
            raise ValueError("Missing required reference profile")
        rows.append((identifier,[name,profile,city],item["source_url"]))
    return sorted(rows,key=lambda r:(r[1][1].casefold(),r[1][0].casefold(),r[0]))

def publish(service,sid,snapshot):
    if sid != SID:
        raise ValueError("Unexpected destination spreadsheet")
    rows=profile_rows(snapshot)
    if not rows:
        raise ValueError("Empty snapshot; existing view retained")
    api=service.spreadsheets()
    meta=api.get(spreadsheetId=sid,fields="sheets(properties)").execute()
    matches=[s["properties"] for s in meta["sheets"] if s["properties"]["title"]==TITLE]
    if not matches:
        added=api.batchUpdate(spreadsheetId=sid,body={"requests":[{"addSheet":{"properties":{
            "title":TITLE,"gridProperties":{"rowCount":max(1000,len(rows)+1),"columnCount":3,"frozenRowCount":1}}}}]}).execute()
        props=added["replies"][0]["addSheet"]["properties"]
    else:
        props=matches[0]
    tab=props["sheetId"]
    count=props["gridProperties"]["rowCount"]
    previous=api.get(spreadsheetId=sid,ranges=[f"'{TITLE}'!A1:C{count}"],fields="sheets(data(rowData(values(userEnteredValue,note))) )".replace(" ","")).execute()
    data=previous["sheets"][0].get("data",[{}])[0].get("rowData",[])
    if data and data[0].get("values"):
        oldhead=data[0]["values"]
        if oldhead[0].get("note")!=MARKER or [v.get("userEnteredValue",{}).get("stringValue","") for v in oldhead[:3]]!=HEADER:
            raise ValueError("Destination tab not owned by catalog sync")
        old_ids={r["values"][0].get("note","").split("\n",1)[0] for r in data[1:] if r.get("values") and r["values"][0].get("userEnteredValue")}
        if not old_ids.issubset({r[0] for r in rows}):
            raise ValueError("Snapshot would lose previously published reference IDs")
    end=len(rows)+1
    def grid(r0,r1,c0=0,c1=3):
        return {"sheetId":tab,"startRowIndex":r0,"endRowIndex":r1,"startColumnIndex":c0,"endColumnIndex":c1}
    def cell(value,note=""):
        return {"userEnteredValue":{"stringValue":str(value)},"note":note}
    values=[{"values":[cell(HEADER[0],MARKER),cell(HEADER[1],"Попередня класифікація; потребує перевірки."),cell(HEADER[2],"Місто лише за наявності відомостей у джерелі.")]}]
    values.extend({"values":[cell(v[0],identifier+"\n"+url),cell(v[1]),cell(v[2])]} for identifier,v,url in rows)
    requests=[]
    if end>count:
        requests.append({"updateSheetProperties":{"properties":{"sheetId":tab,"gridProperties":{"rowCount":end+100}},"fields":"gridProperties.rowCount"}})
    requests += [
        {"updateCells":{"range":grid(0,end),"rows":values,"fields":"userEnteredValue,note"}},
        {"repeatCell":{"range":grid(0,1),"cell":{"userEnteredFormat":{"backgroundColor":{"red":.91,"green":.93,"blue":.95},"textFormat":{"bold":True},"wrapStrategy":"WRAP","verticalAlignment":"MIDDLE"}},"fields":"userEnteredFormat"}},
        {"repeatCell":{"range":grid(1,end),"cell":{"userEnteredFormat":{"wrapStrategy":"WRAP","verticalAlignment":"TOP"}},"fields":"userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
        {"updateSheetProperties":{"properties":{"sheetId":tab,"gridProperties":{"frozenRowCount":1}},"fields":"gridProperties.frozenRowCount"}},
        {"setBasicFilter":{"filter":{"range":grid(0,end)}}},
        {"updateDimensionProperties":{"range":{"sheetId":tab,"dimension":"ROWS","startIndex":0,"endIndex":1},"properties":{"pixelSize":40},"fields":"pixelSize"}},
    ]
    for i,w in enumerate((420,360,180)):
        requests.append({"updateDimensionProperties":{"range":{"sheetId":tab,"dimension":"COLUMNS","startIndex":i,"endIndex":i+1},"properties":{"pixelSize":w},"fields":"pixelSize"}})
    requests.append({"autoResizeDimensions":{"dimensions":{"sheetId":tab,"dimension":"ROWS","startIndex":1,"endIndex":end}}})
    api.batchUpdate(spreadsheetId=sid,body={"requests":requests}).execute()
    actual=api.values().get(spreadsheetId=sid,range=f"'{TITLE}'!A1:C{end}").execute()["values"]
    expected=[HEADER]+[r[1] for r in rows]
    if [list(r)+[""]*(3-len(r)) for r in actual]!=expected:
        raise RuntimeError("Sheet readback mismatch")
    print("SHEETS_SYNC_OK",len(rows),"CITIES",sum(bool(r[1][2]) for r in rows),"TAB",tab,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",required=True,type=Path)
    a=p.parse_args()
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    info=json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    if info.get("client_email")!="ngo-grants-outreach@ngo-grants-outreach.iam.gserviceaccount.com":
        raise ValueError("Unexpected service account")
    creds=Credentials.from_service_account_info(info,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    publish(build("sheets","v4",credentials=creds,cache_discovery=False),os.environ["CRM_ID"],json.loads(a.snapshot.read_text(encoding="utf-8")))

if __name__=="__main__":
    main()
