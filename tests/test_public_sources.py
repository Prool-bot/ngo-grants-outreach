import unittest
from public_sources import parse_prozorro_detail, parse_ted_notice

class PublicSources(unittest.TestCase):
    def test_prozorro_relevant(self):
        obj={"data":{"tenderID":"UA-2026-11-27-000123-a","title":"Інформаційні послуги","status":"active.tendering","procuringEntity":{"name":"Test buyer"},"items":[{"classification":{"id":"79340000-9"}}]}}
        self.assertEqual(parse_prozorro_detail(obj)["buyer"],"Test buyer")
        obj["data"]["status"]="complete"
        self.assertIsNone(parse_prozorro_detail(obj))
    def test_ted_multilingual(self):
        obj={"publication-number":"123456-2026","notice-title":{"eng":"Communications"},"buyer-name":["Example buyer"]}
        self.assertEqual(parse_ted_notice(obj)["title"],"Communications")
        self.assertIsNone(parse_ted_notice({"publication-number":"invalid"}))
