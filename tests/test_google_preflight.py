import unittest
from unittest.mock import MagicMock
from google_preflight import verify_crm, load_price
class TestGooglePreflight(unittest.TestCase):
    def test_crm_identity(self):
        s = MagicMock()
        s.spreadsheets().values().get().execute.return_value = {"values":[["Основна пошта","a@example.org"],["Прайс Drive ID","test"]]}
        self.assertEqual(verify_crm(s, "dummy", "a@example.org")["Прайс Drive ID"], "test")
        with self.assertRaises(ValueError):
            verify_crm(s, "dummy", "b@example.org")
    def test_price_wrong_size(self):
        d = MagicMock()
        d.files().get().execute.return_value = {"mimeType":"application/pdf","size":"20"}
        with self.assertRaises(ValueError):
            load_price(d, "dummy")
        d.files().get_media.assert_not_called()
