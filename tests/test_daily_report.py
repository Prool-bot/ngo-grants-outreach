import unittest
from daily_report import summarize, cycle_coverage
from datetime import datetime
from zoneinfo import ZoneInfo
class TestReport(unittest.TestCase):
    def test_retries(self):
        rows=[["x","2026-11-27","","","DISCOVERY","PARTIAL","3","0"],["x","2026-11-27","","","DISCOVERY","OK","2","0"],["y","2026-11-26","","","DISCOVERY","OK","9","0"]]
        n,status,count=summarize(rows,"2026-11-27")
        self.assertEqual((n,status["OK"],count),(1,1,5))

    def test_schedule_coverage(self):
        now=datetime(2026,11,30,17,30,tzinfo=ZoneInfo("Europe/Istanbul"))
        rows=[["2026-11-30T09:00+0300","","","","DISCOVERY","OK"],["2026-11-30T10:00+0300","","","","DISCOVERY","PARTIAL"],["PILOT-1","","","","PILOT","OK"]]
        self.assertEqual(cycle_coverage(rows,now),(9,2,7,1))

    def test_before_activation(self):
        now=datetime(2026,11,27,19,30,tzinfo=ZoneInfo("Europe/Istanbul"))
        self.assertEqual(cycle_coverage([],now),(0,0,0,0))
