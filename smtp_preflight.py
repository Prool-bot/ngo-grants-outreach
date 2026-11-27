"""Check existing SMTP credentials without accessing or disclosing their values."""
import os
import ssl
import smtplib
from email.message import EmailMessage

def validate_sender(address, expected):
    address = address.strip().lower()
    expected = expected.strip().lower()
    if not address or not expected or address != expected:
        raise ValueError("SMTP account does not match the expected commercial mailbox")
    return address

def preflight(address, expected, password, send_test=False):
    address = validate_sender(address, expected)
    if not password:
        raise ValueError("EMAIL_APP_PASSWORD missing")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(address, password)
        if send_test:
            msg = EmailMessage()
            msg["From"] = address
            msg["To"] = address
            msg["Subject"] = "NGO Grants Outreach — SMTP test"
            msg.set_content("Технічна перевірка SMTP. Зовнішніх отримувачів немає.")
            rejected = server.send_message(msg, from_addr=address, to_addrs=[address])
            if rejected:
                raise RuntimeError("Self-test rejected")
    return "SELF_TEST_ACCEPTED" if send_test else "AUTH_OK"

if __name__ == "__main__":
    try:
        print(preflight(os.getenv("EMAIL_ADDRESS", ""), os.getenv("EXPECTED_GMAIL", ""),
                        os.getenv("EMAIL_APP_PASSWORD", ""),
                        os.getenv("SEND_SELF_TEST", "") == "true"))
    except Exception as exc:
        print("SMTP_ERROR:", type(exc).__name__, "Check configured secrets; no external mail sent.")
        raise SystemExit(1)
