import unittest
from datetime import datetime
from outreach import canonical_url, parse_listing, is_work_hour, ZONE

class TestOutreach(unittest.TestCase):
    def test_dedup(self):
        self.assertEqual(canonical_url("https://www.prostir.ua/?grants=abc&utm_source=foo#top"), "https://prostir.ua/?grants=abc")
        self.assertNotEqual(canonical_url("https://prostir.ua/?grants=abc"),canonical_url("https://prostir.ua/?grants=def"))
    def test_listing(self):
        html = '<a href="/?grants=abc">Тендер на закупівлю послуг</a><a href="/?grants=abc&utm_medium=test">Тендер на закупівлю послуг</a><a href="https://other.com/a">Тендер на послуги</a><a href="/news">Просто новина</a>'
        self.assertEqual(parse_listing(html,"https://www.prostir.ua/category/grants/?tenders=1"),[("Тендер на закупівлю послуг","https://prostir.ua/?grants=abc")])
    def test_schedule(self):
        for hour in [9,17]:
            self.assertTrue(is_work_hour(datetime(2026,11,30,hour,tzinfo=ZONE)))
        self.assertFalse(is_work_hour(datetime(2026,11,30,18,tzinfo=ZONE)))
        self.assertFalse(is_work_hour(datetime(2026,11,28,12,tzinfo=ZONE)))

if __name__=="__main__":
    unittest.main()
