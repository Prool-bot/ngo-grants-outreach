import unittest
from datetime import date
from procurement_quality import triage
class TestProcurementQuality(unittest.TestCase):
    def test_statuses(self):
        today=date(2026,11,27)
        self.assertEqual(triage("Правила публікації тендерів","","",today)[0],"EXCLUDED_NAVIGATION")
        self.assertEqual(triage("Закупівля меблів","","",today)[0],"LOW_RELEVANCE")
        self.assertEqual(triage("Послуги SMM","","",today)[0],"UNVERIFIED_DEADLINE")
        self.assertEqual(triage("Послуги SMM","2026-11-26","",today)[0],"EXPIRED")
        self.assertEqual(triage("Послуги SMM","2026-11-27","",today)[0],"VERIFY_TODAY")
        self.assertEqual(triage("Advertising services","2026-12-12","",today)[0],"VERIFY_ELIGIBILITY")
        self.assertEqual(triage("Advertising services","2026-12-12; 2026-12-15","",today)[0],"UNVERIFIED_DEADLINE")
