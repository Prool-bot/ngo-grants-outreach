import unittest
from daily_report import summarize
class TestReport(unittest.TestCase):
    def test_retries(self):
        rows=[["x","2026-11-27","","","DISCOVERY","PARTIAL","3","0"],["x","2026-11-27","","","DISCOVERY","OK","2","0"],["y","2026-11-26","","","DISCOVERY","OK","9","0"]]
        n,status,count=summarize(rows,"2026-11-27")
        self.assertEqual((n,status["OK"],count),(1,1,5))
