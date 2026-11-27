import unittest
from datetime import date
from queue_audit import evaluate
class TestQueue(unittest.TestCase):
    def test_exclusions_and_evidence(self):
        row=["1","Example","NGO-01","test@example.org","DIRECT_REQUEST","inbound evidence","2026-11-26","APPROVED"]
        today=date(2026,11,27)
        self.assertEqual(evaluate([row],{"test@example.org"},set(),today)["EXCLUDED"],1)
        self.assertEqual(evaluate([row,row],set(),set(),today)["DUPLICATE"],1)
        row[5]=""
        self.assertEqual(evaluate([row],set(),set(),today)["EVIDENCE_MISSING"],1)
