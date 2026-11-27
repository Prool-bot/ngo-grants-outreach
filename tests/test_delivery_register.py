import unittest
from delivery_register import plan
class DeliveryRegisterTest(unittest.TestCase):
    def test_confirmed_only_and_dedup(self):
        rows=[["test@example.org","Org","2026-11-27","550 5.1.1","No such user","id1","Виключити"],["other@example.org","Org","2026-11-27","554 5.7.1","Relay access denied","id2","Не повторювати"],["uncertain@example.org","Org","2026-11-27","550 5.1.1","No such user","id3","Не повторювати до з'ясування"]]
        self.assertEqual(len(plan(rows,[])),1)
        self.assertEqual(plan(rows,[["TEST@example.org"]]),[])
        self.assertEqual(len(plan(rows+rows,[])),1)
