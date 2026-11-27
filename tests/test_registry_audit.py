import unittest
from datetime import date
from registry_audit import plan
class RegistryAuditTest(unittest.TestCase):
    def test_review_preserved(self):
        def row(key,state):
            return [key,"","TED","Advertising services","","2026-11-26","https://example.org","","",state,""]
        changes,counts=plan([row("1","NEW"),row("2","MANUAL_APPROVED")],date(2026,11,27))
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0][1:4],("1","NEW","EXPIRED"))
        self.assertEqual(counts["EXPIRED"],2)
