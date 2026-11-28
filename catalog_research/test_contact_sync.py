import unittest
from bs4 import BeautifulSoup
from catalog_research.contact_sync import extract, generic_email, phone, key, eligible_new, canonical_profile, balanced

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

    def test_new_entry_requires_phone_and_email_not_city(self):
        self.assertTrue(eligible_new({"email":("info@example.org","url"),"phone":("+380441234567","url")}))
        self.assertFalse(eligible_new({"email":("info@example.org","url"),"city":("Київ","url")}))
        self.assertFalse(eligible_new({"phone":("+380441234567","url")}))
    def test_explicit_organization_phone(self):
        html='<p>Телефон: +38 (044) 123-45-67</p><p>Іван: +38 (050) 123-45-67</p>'
        soup=BeautifulSoup(html,"html.parser")
        self.assertEqual(extract(soup,contact_page=True)[1],["+380441234567"])
        self.assertEqual(extract(soup)[1],[])
    def test_category_and_balancing(self):
        self.assertEqual(canonical_profile("Фаховий коледж", "EDU-01 — Університети", {"Коледжі":"EDU-02"}),"Коледжі")
        self.assertEqual(canonical_profile("Example","unknown",{}),"")
        items=[(None,"a","X"),(None,"b","X"),(None,"c","Y")]
        self.assertEqual([i[2] for i in balanced(items,0)],["X","Y","X"])
