import unittest
from unittest.mock import MagicMock
from google_preflight import verify_crm
class TestGooglePreflight(unittest.TestCase):
    def test_crm_identity(self):
        s = MagicMock()
        s.spreadsheets().values().get().execute.return_value = {"values":[["Основна пошта","a@example.org"]]}
        self.assertEqual(verify_crm(s, "dummy", "a@example.org")["Основна пошта"], "a@example.org")
        with self.assertRaises(ValueError):
            verify_crm(s, "dummy", "b@example.org")
