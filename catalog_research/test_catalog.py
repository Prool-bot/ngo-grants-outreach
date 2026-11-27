import unittest
from catalog_research.run import load_categories,select_reference,csv_cell
class CatalogTests(unittest.TestCase):
    def test_classifier(self):
        self.assertEqual(len(load_categories()),115)
    def test_only_topic_related_reference(self):
        cat={"code":"EDU-01","label":"Університети","query":"університет"}
        page={"ns":0,"title":"Університет прикладу","pageprops":{"wikibase_item":"Q123"},"terms":{"description":["університет в Україні"]}}
        r=select_reference(page,cat)
        self.assertEqual(r["source_id"],"Q123")
        self.assertEqual(r["status"],"REFERENCE_REVIEW_REQUIRED")
        self.assertNotIn("email",r)
        page["terms"]["description"]=["український політик, ректор університету"]
        self.assertIsNone(select_reference(page,cat))
        page["terms"]["description"]=["театр в Україні"]
        page["title"]="Театр"
        self.assertIsNone(select_reference(page,cat))
    def test_csv(self):
        self.assertEqual(csv_cell("=1+1"),"'=1+1")

class AccumulationTests(unittest.TestCase):
    def test_preserve_and_merge(self):
        from catalog_research.accumulate import accumulate
        prior={"references":[{"source_id":"Q1","title":"Example","category_codes":["EDU-01"]},{"source_id":"Q2","title":"Other","category_codes":["ART-05"]}]}
        current={"references":[{"source_id":"Q1","title":"Example","category_codes":["EDU-07"]},{"source_id":"Q3","title":"New","category_codes":["NGO-03"]}]}
        result=accumulate(prior,current,"2026-11-27")
        self.assertEqual(len(result["references"]),3)
        self.assertEqual(result["references"][0]["category_codes"],["EDU-01","EDU-07"])
        self.assertEqual(len(result["coverage"]),115)
        self.assertEqual(len(accumulate(result,{}, "2026-11-28")["references"]),3)

class RegistryReferenceTests(unittest.TestCase):
    def test_ror_and_crossref(self):
        from catalog_research.registry_references import parse_ror,parse_crossref
        from catalog_research.accumulate import accumulate
        item={"id":"https://ror.org/012345678","status":"active","types":["education"],
              "locations":[{"geonames_details":{"country_code":"UA"}}],
              "names":[{"value":"Example University","types":["ror_display"]}],
              "external_ids":[{"type":"wikidata","all":["Q123"]}]}
        r=parse_ror(item,"EDU-01","education","University")
        self.assertEqual(r["source_id"],"Q123")
        self.assertEqual(r["sources"],["ROR"])
        item["status"]="inactive"
        self.assertIsNone(parse_ror(item,"EDU-01","education","University"))
        f=parse_crossref({"id":"100000001","name":"Example Research Foundation","location":"Ukraine"})
        self.assertEqual(f["source_id"],"CROSSREF:10.13039/100000001")
        self.assertIsNone(parse_crossref({"id":"100000001","name":"Foundation","location":"France"}))
        result=accumulate({"references":[{"source_id":"Q123","title":"Example","category_codes":["EDU-01"]}]},{"references":[r,f]},"2026-11-27")
        self.assertEqual(len(result["references"]),2)
        q=next(x for x in result["references"] if x["source_id"]=="Q123")
        self.assertEqual(q["sources"],["ROR","Wikimedia"])

class SectorResourcesTests(unittest.TestCase):
    def test_merge_preserves_topics(self):
        from catalog_research.sector_resources import row,merge
        a=row("TED","1-2026","Example notice","HYGIENE","PROCUREMENT_NOTICE","https://ted.europa.eu/en/notice/-/detail/1-2026")
        b={**a,"topics":["MEDICAL"]}
        merged=merge([a],[b])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]["topics"],["HYGIENE","MEDICAL"])
        self.assertNotIn("buyer",merged[0])
        self.assertNotIn("email",merged[0])
    def test_text_field(self):
        from catalog_research.sector_resources import text_value
        self.assertEqual(text_value({"ENG":["Example"]}),"Example")

class CityEvidenceTests(unittest.TestCase):
    def test_preserve_source_city(self):
        from catalog_research.registry_references import parse_ror
        from catalog_research.accumulate import accumulate
        item={"id":"https://ror.org/012345678","status":"active","types":["education"],
              "locations":[{"geonames_details":{"country_code":"UA","name":"Kyiv"}}],
              "names":[{"value":"Example University","types":["ror_display"]}]}
        r=parse_ror(item,"EDU-01","education","University")
        self.assertEqual(r["cities"],["Kyiv"])
        a=accumulate({},{"references":[r]},"2026-11-27")
        b=accumulate(a,{},"2026-11-28")
        self.assertEqual(b["references"][0]["cities"],["Kyiv"])
