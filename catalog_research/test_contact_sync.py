import unittest
from bs4 import BeautifulSoup
from catalog_research.contact_sync import extract, generic_email, phone, key

class ContactTests(unittest.TestCase):
    def test_organization_only(self):
        html='''<header><a href="tel:+380441234567">Call center</a></header>
        <a href="mailto:info@example.org">info</a>
        <a href="mailto:jane.doe@example.org">Jane Doe</a>
        <section><a href="tel:+380501234567">Jane Doe</a></section>
        <script type="application/ld+json">{"@type":"Organization","address":{"@type":"PostalAddress","addressLocality":"Kyiv"},"email":"office@example.org"}</script>'''
        emails, phones, cities=extract(BeautifulSoup(html,"html.parser"))
        self.assertEqual(set(emails),{"info@example.org","office@example.org"})
        self.assertEqual(phones,["+380441234567"])
        self.assertEqual(cities,["Київ"])
    def test_validation(self):
        self.assertEqual(phone("067-123-45-67"),"+380671234567")
        self.assertEqual(phone("123456789"),"")
        self.assertEqual(generic_email("mailto:info@example.org?subject=x"),"info@example.org")
        self.assertEqual(generic_email("person@example.org"),"")
        self.assertEqual(key("Example, Ltd."),key("Example Ltd"))
