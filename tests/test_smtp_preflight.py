import unittest
from unittest.mock import patch
from smtp_preflight import validate_sender, preflight

class SMTPTest(unittest.TestCase):
    def test_wrong_account(self):
        with self.assertRaises(ValueError):
            validate_sender("other@example.com", "self@example.com")
    @patch("smtp_preflight.smtplib.SMTP")
    def test_auth_without_sending(self, smtp):
        server = smtp.return_value.__enter__.return_value
        self.assertEqual(preflight("self@example.com","self@example.com","dummy"),"AUTH_OK")
        server.login.assert_called_once_with("self@example.com","dummy")
        server.send_message.assert_not_called()
    @patch("smtp_preflight.smtplib.SMTP")
    def test_self_only(self, smtp):
        server = smtp.return_value.__enter__.return_value
        server.send_message.return_value = {}
        self.assertEqual(preflight("self@example.com","self@example.com","dummy", True),"SELF_TEST_ACCEPTED")
        args, kwargs = server.send_message.call_args
        self.assertEqual(kwargs["to_addrs"],["self@example.com"])
        self.assertIsNone(args[0]["Bcc"])
        self.assertEqual(args[0]["To"],"self@example.com")
