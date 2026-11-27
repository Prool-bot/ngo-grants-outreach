import unittest
from directory_sources import parse_record
class TestDirectory(unittest.TestCase):
    def test_org(self):
        x={"id":"https://ror.org/012345678","status":"active","locations":[{"geonames_details":{"country_code":"UA"}}],"names":[{"value":"Test University","types":["ror_display"]}],"links":[{"type":"website","value":"https://example.org"}],"types":["education"]}
        self.assertEqual(parse_record(x,"EDU-01")["code"],"EDU-01")
        x["status"]="inactive"
        self.assertIsNone(parse_record(x,"EDU-01"))
    def test_agri(self):
        x={"id":"https://ror.org/012345678","status":"active","locations":[{"geonames_details":{"country_code":"UA"}}],"names":[{"value":"Agricultural University","types":["ror_display"]}]}
        self.assertIsNone(parse_record(x,"EDU-01"))
