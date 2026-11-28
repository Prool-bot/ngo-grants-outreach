import unittest
from bs4 import BeautifulSoup
from catalog_research.contact_sync import extract, generic_email, phone, key, eligible_new, canonical_profile, balanced, classify_candidate, description_for, neutral_sentence, site_evidence

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

    def test_animal_rehabilitation_not_human(self):
        cats=[{"code":"DEV-07","label":"Реабілітаційні центри","query":"реабілітаційний центр"}]
        result={"evidence":("Парк диких тварин; центр реабілітації тварин; реабілітаційний центр","https://example.org")}
        self.assertEqual(classify_candidate("Парк хижаків Арден","Реабілітаційні центри",result,cats),("","animal_not_human_rehabilitation"))
        result={"evidence":("Реабілітаційний центр, фізична терапія пацієнтів","https://example.org")}
        self.assertEqual(classify_candidate("Центр","Реабілітаційні центри",result,cats)[1],"confirmed")
    def test_portal_and_cultural_center_disambiguation(self):
        cats=[{"code":"FIN-09","label":"FinTech-компанії","query":"фінтех"},
              {"code":"MED-03","label":"Тематичні інформаційні портали","query":"інформаційний портал"},
              {"code":"NGO-11","label":"Ресурсні центри для ГО","query":"ресурсний центр громадських організацій"},
              {"code":"ART-07","label":"Культурні центри","query":"культурний центр"}]
        self.assertEqual(classify_candidate("Мінфін","FinTech-компанії",{"evidence":("Фінансовий портал про економіку","url")},cats),("Тематичні інформаційні портали","corrected"))
        self.assertEqual(classify_candidate("Шелтер","Ресурсні центри для ГО",{"evidence":("Культурно-громадський центр","url")},cats),("Культурні центри","corrected"))
        self.assertEqual(classify_candidate("Невідома компанія","FinTech-компанії",{"evidence":("Контакти і послуги","url")},cats),("","category_unconfirmed"))
    def test_neutral_description(self):
        self.assertEqual(neutral_sentence("Ласкаво просимо! Найкращий магазин художніх матеріалів."),"")
        self.assertEqual(neutral_sentence("Магазин художніх матеріалів &amp; товарів для творчості 🎨."),"Магазин художніх матеріалів & товарів для творчості.")
        cat={"code":"ART-01","label":"Художні магазини","query":"художній магазин"}
        desc,url,method=description_for(cat["label"],{"description":("Контактна інформація.","url"),"evidence":("Художні матеріали","source")},cat)
        self.assertEqual(desc,"Магазин художніх матеріалів і товарів для творчості.")
        self.assertEqual(url,"source")
    def test_evidence_from_about(self):
        soup=BeautifulSoup('<title>Мистецький центр</title><main><p>Культурний центр проводить освітні та мистецькі заходи для молоді.</p></main>',"html.parser")
        evidence,desc=site_evidence(soup,about=True)
        self.assertIn("Культурний центр",evidence)
        self.assertTrue(desc.endswith("."))
