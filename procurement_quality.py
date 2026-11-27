"""Procurement triage: title relevance and explicit deadline validation.
A positive result is not a finding of eligibility or an invitation to send advertising.
"""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONE=ZoneInfo("Europe/Istanbul")
NAV=re.compile(r"правила публікаці|як опублікувати|архів тендерів",re.I)
AGRI=re.compile(r"аграр|сільськогосподар|agricultur|agronom",re.I)
RELEVANT=re.compile(r"комунікац|інформаційн\w* (?:послуг|кампан|супров|матеріал|підтрим)|реклам|маркетинг|\bsmm\b|\bpr\b|моніторинг грант|advertis|public relations|communication|media campaign|digital campaign|marketing",re.I)
CPV={"79341000","79342000","79416000"}

def triage(title, deadline, cpv, today):
    if NAV.search(title):
        return "EXCLUDED_NAVIGATION", "Службове посилання, не закупівля"
    if AGRI.search(title):
        return "EXCLUDED_SECTOR", "Аграрний напрям"
    if not RELEVANT.search(title) and not CPV.intersection(re.findall(r"\b\d{8}\b",cpv)):
        return "LOW_RELEVANCE", "Немає чіткої відповідності профілю послуг"
    if not deadline:
        return "UNVERIFIED_DEADLINE", "Дедлайн відсутній; не вважати активною"
    dates=[]
    for value in re.findall(r"\d{4}-\d{2}-\d{2}",deadline):
        try:
            dates.append(date.fromisoformat(value))
        except ValueError:
            return "UNVERIFIED_DEADLINE", "Некоректний формат дедлайну"
    if not dates or len(set(dates))!=1:
        return "UNVERIFIED_DEADLINE", "Неоднозначний дедлайн; перевірити лоти"
    if dates[0]<today:
        return "EXPIRED", "Строк подання минув"
    if dates[0]==today:
        return "VERIFY_TODAY", "Дедлайн сьогодні; перевірити час і часовий пояс"
    return "VERIFY_ELIGIBILITY", "Профільний предмет; перевірити географію, умови та право подання"
