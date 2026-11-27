import unittest
from email import policy
from email.parser import Parser
from mailbox_dsn import parse_dsn,new_records,known_correspondence

SAMPLE="""From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>
Date: Fri, 27 Nov 2026 10:00:00 +0300
Message-ID: <test@example.org>
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="b"

--b
Content-Type: text/plain

Delivery failed.
--b
Content-Type: message/delivery-status

Reporting-MTA: dns; example.org

Final-Recipient: rfc822; test@example.org
Action: failed
Status: 5.1.1

--b--
"""
class MailboxDsnTests(unittest.TestCase):
    def test_structured_dsn(self):
        m=Parser(policy=policy.default).parsestr(SAMPLE)
        r=parse_dsn(m,{"test@example.org":"Example"})
        self.assertEqual(len(r),1)
        self.assertEqual(r[0][3],"5.1.1")
        self.assertEqual(new_records(r,r),[])
        self.assertEqual(parse_dsn(m,{}),[])
    def test_ignore_unrelated_or_ambiguous(self):
        for s in (SAMPLE.replace("mailer-daemon@googlemail.com","other@example.org"),
                  SAMPLE.replace("Action: failed","Action: delayed"),
                  SAMPLE.replace("Action: failed","Original-Recipient: rfc822; other@example.org\nAction: failed")):
            self.assertEqual(parse_dsn(Parser(policy=policy.default).parsestr(s),{"test@example.org":"Example"}),[])
    def test_match_sent_only(self):
        self.assertEqual(known_correspondence([["1","Example","NGO","test@example.org","","","id","Надіслано"]],[]),{"test@example.org":"Example"})
