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
