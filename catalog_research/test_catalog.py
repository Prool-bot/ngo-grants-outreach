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
