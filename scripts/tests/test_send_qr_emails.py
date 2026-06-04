"""
Tests for scripts/actions/send_qr_emails.py.

Covers: session_url, qr_image_url, manage_url, format_manager_email,
and the send_qr_emails pipeline (grouping, skipping, dry-run).
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import fixtures
from actions.send_qr_emails import (
    SessionEntry,
    format_manager_email,
    manage_url,
    qr_image_url,
    send_qr_emails,
    session_url,
)
from mock_db import MockDatabase
from support import Record


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

class TestUrlHelpers(unittest.TestCase):

    def test_session_url_no_first(self):
        url = session_url("http://host:8000", "sessABC")
        self.assertEqual(url, "http://host:8000/meals.html?session=sessABC")

    def test_session_url_with_first(self):
        url = session_url("http://host:8000", "sessABC", first=True)
        self.assertIn("&first=1", url)

    def test_session_url_strips_trailing_slash(self):
        url = session_url("http://host:8000/", "sessABC")
        self.assertFalse(url.startswith("http://host:8000//"))

    def test_qr_image_url_contains_encoded_data(self):
        url = qr_image_url("http://host/meals.html?session=x")
        self.assertIn("create-qr-code", url)
        self.assertIn("250x250", url)

    def test_manage_url(self):
        url = manage_url("http://host:8000", "mgrXYZ")
        self.assertEqual(url, "http://host:8000/manage.html?manager=mgrXYZ")


# ---------------------------------------------------------------------------
# format_manager_email
# ---------------------------------------------------------------------------

class TestFormatManagerEmail(unittest.TestCase):

    def _entries(self) -> list[SessionEntry]:
        return [
            SessionEntry(label="Monday — Alpha Academy", url="http://host/meals.html?session=s1"),
            SessionEntry(label="Wednesday — Beta College", url="http://host/meals.html?session=s2"),
        ]

    def test_subject_fixed(self):
        subject, _ = format_manager_email("Carol Manager", self._entries(), "mgr1", "http://host")
        self.assertEqual(subject, "Padea Meals — QR codes for this term's sessions")

    def test_body_contains_first_name(self):
        _, body = format_manager_email("Carol Manager", self._entries(), "mgr1", "http://host")
        self.assertIn("Hi Carol", body)

    def test_body_contains_entry_labels(self):
        _, body = format_manager_email("Carol Manager", self._entries(), "mgr1", "http://host")
        self.assertIn("Monday — Alpha Academy", body)
        self.assertIn("Wednesday — Beta College", body)

    def test_body_contains_manage_link(self):
        _, body = format_manager_email("Carol Manager", self._entries(), "mgr1", "http://host")
        self.assertIn("manage.html?manager=mgr1", body)

    def test_no_name_falls_back_to_there(self):
        _, body = format_manager_email("", self._entries(), "mgr1", "http://host")
        self.assertIn("Hi there", body)


# ---------------------------------------------------------------------------
# send_qr_emails pipeline
# ---------------------------------------------------------------------------

class TestSendQrEmailsPipeline(unittest.TestCase):

    def setUp(self) -> None:
        self._send_patch = mock.patch("support.email._send_via_mailslurp")
        self._send_patch.start()
        self._env_patch = mock.patch.dict(os.environ, {"MAILSLURP_API_KEY": "test-key"}, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._send_patch.stop()
        self._env_patch.stop()

    def _make_db(self, *, mgr_email: str | None = "carol@alpha.edu.au") -> MockDatabase:
        db = MockDatabase()
        db.Schools._records   = [fixtures.school_alpha()]
        db.Sessions._records  = [
            Record(id=fixtures.SESSION_MON_ID, fields={
                "session_code":       "Alpha Academy - Monday",
                "school_id":          fixtures.SCHOOL_A_ID,
                "day":                "Monday",
                "on_site_manager_id": fixtures.MANAGER_A_ID,
            })
        ]
        mgr_fields = {"name": "Carol Manager", "mobile": "0412345678"}
        if mgr_email:
            mgr_fields["email"] = mgr_email
        db.OnSiteManagers._records = [Record(id=fixtures.MANAGER_A_ID, fields=mgr_fields)]
        return db

    def test_dry_run_sends_no_email(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_qr_emails(dry_run=True, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_live_run_queues_one_email_per_manager(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_qr_emails(dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 1)
        f = db.ScheduledEmails.created_fields[0]
        self.assertEqual(f["to_address"], "carol@alpha.edu.au")

    def test_two_sessions_same_manager_one_email(self):
        db = self._make_db()
        db.Sessions._records.append(
            Record(id=fixtures.SESSION_WED_ID, fields={
                "session_code":       "Alpha Academy - Wednesday",
                "school_id":          fixtures.SCHOOL_A_ID,
                "day":                "Wednesday",
                "on_site_manager_id": fixtures.MANAGER_A_ID,
            })
        )
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_qr_emails(dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 1)

    def test_session_with_no_manager_skipped(self):
        db = self._make_db()
        db.Sessions._records[0].fields.pop("on_site_manager_id", None)
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_qr_emails(dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_manager_with_no_email_skipped(self):
        db = self._make_db(mgr_email=None)
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_qr_emails(dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_first_flag_appended_to_url(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_qr_emails(dry_run=False, first=True, db=db)
        body = db.ScheduledEmails.created_fields[0]["body"]
        self.assertIn("first=1", body)


if __name__ == "__main__":
    unittest.main()
