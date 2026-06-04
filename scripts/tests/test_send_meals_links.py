"""
Tests for scripts/actions/send_meals_links.py.

Covers: meals_url, manage_url, format_parent_email, format_student_email,
and the send_links pipeline (target routing, skipping, dry-run, first flag).
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import fixtures
from actions.forms.send_meals_links import (
    SessionLink,
    format_parent_email,
    format_student_email,
    manage_url,
    meals_url,
    send_links,
)
from mock_db import MockDatabase
from support import Record


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

class TestUrlHelpers(unittest.TestCase):

    def test_meals_url_basic(self):
        url = meals_url("http://host:8000", "sess1", "stu1")
        self.assertEqual(url, "http://host:8000/meals.html?session=sess1&student=stu1")

    def test_meals_url_first_flag(self):
        url = meals_url("http://host:8000", "sess1", "stu1", first=True)
        self.assertIn("&first=1", url)

    def test_manage_url(self):
        url = manage_url("http://host:8000", "stu1")
        self.assertEqual(url, "http://host:8000/manage.html?student=stu1")


# ---------------------------------------------------------------------------
# format_parent_email
# ---------------------------------------------------------------------------

class TestFormatParentEmail(unittest.TestCase):

    def _links(self) -> list[SessionLink]:
        return [SessionLink(label="Monday — Alpha (Café)", url="http://host/meals.html?session=s1&student=st1")]

    def test_first_session_subject(self):
        subject, _ = format_parent_email("Jane Parent", "Alice", self._links(), "http://host/manage.html?student=st1", first_session=True)
        self.assertIn("set", subject.lower())

    def test_non_first_subject(self):
        subject, _ = format_parent_email("Jane Parent", "Alice", self._links(), "http://host/manage.html?student=st1", first_session=False)
        self.assertIn("update", subject.lower())

    def test_body_contains_parent_first_name(self):
        _, body = format_parent_email("Jane Parent", "Alice", self._links(), "http://host/manage.html?student=st1")
        self.assertIn("Hi Jane", body)

    def test_body_contains_session_link(self):
        _, body = format_parent_email("Jane Parent", "Alice", self._links(), "http://host/manage.html?student=st1")
        self.assertIn("Monday — Alpha (Café)", body)

    def test_no_parent_name_falls_back(self):
        _, body = format_parent_email("", "Alice", self._links(), "http://host/manage.html?student=st1")
        self.assertIn("Hi there", body)


# ---------------------------------------------------------------------------
# format_student_email
# ---------------------------------------------------------------------------

class TestFormatStudentEmail(unittest.TestCase):

    def _links(self) -> list[SessionLink]:
        return [SessionLink(label="Monday — Alpha", url="http://host/meals.html?session=s1&student=st1")]

    def test_first_session_subject(self):
        subject, _ = format_student_email("Alice", self._links(), "http://host/manage.html?student=st1", first_session=True)
        self.assertIn("set", subject.lower())

    def test_body_contains_student_first_name(self):
        _, body = format_student_email("Alice Student", self._links(), "http://host/manage.html?student=st1")
        self.assertIn("Hi Alice", body)


# ---------------------------------------------------------------------------
# send_links pipeline
# ---------------------------------------------------------------------------

class TestSendLinksPipeline(unittest.TestCase):

    def setUp(self) -> None:
        self._send_patch = mock.patch("support.email._send_via_sendgrid")
        self._send_patch.start()
        self._env_patch = mock.patch.dict(os.environ, {"SENDGRID_API_KEY": "test-key"}, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._send_patch.stop()
        self._env_patch.stop()

    def _make_db(
        self,
        *,
        student_email: str | None = "alice@student.edu.au",
        parent_email: str | None = "jane@parent.com",
        session_ids: list[str] | None = None,
    ) -> MockDatabase:
        db = MockDatabase()
        db.Schools._records  = [fixtures.school_alpha()]
        db.Caterers._records = [fixtures.caterer_a()]
        db.Sessions._records = [
            Record(id=fixtures.SESSION_MON_ID, fields={
                "session_code": "Alpha Academy - Monday",
                "school_id":    fixtures.SCHOOL_A_ID,
                "caterer_id":   fixtures.CATERER_A_ID,
                "day":          "Monday",
            })
        ]
        fields: dict = {
            "name":        "Alice Student",
            "session_ids": session_ids if session_ids is not None else [fixtures.SESSION_MON_ID],
        }
        if student_email:
            fields["email"] = student_email
        if parent_email:
            fields["parent_email"] = parent_email
            fields["parent_name"]  = "Jane Parent"
        db.Students._records = [Record(id=fixtures.STU_NORMAL_ID, fields=fields)]
        return db

    def test_students_target_dry_run_no_email(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=True, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_students_target_sends_to_student_email(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 1)
        self.assertEqual(db.ScheduledEmails.created_fields[0]["to_address"], "alice@student.edu.au")

    def test_parents_target_sends_to_parent_email(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="parents", dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 1)
        self.assertEqual(db.ScheduledEmails.created_fields[0]["to_address"], "jane@parent.com")

    def test_student_with_no_email_skipped(self):
        db = self._make_db(student_email=None)
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_student_with_no_sessions_skipped(self):
        db = self._make_db(session_ids=[])
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_student_with_unresolvable_session_skipped(self):
        db = self._make_db(session_ids=["nonexistent_session"])
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_first_flag_included_in_body_url(self):
        db = self._make_db()
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=False, first=True, db=db)
        body = db.ScheduledEmails.created_fields[0]["body"]
        self.assertIn("first=1", body)

    def test_no_students_returns_early(self):
        db = self._make_db()
        db.Students._records = []
        os.environ["URL_ORIGIN"] = "http://host:8000"
        send_links(target="students", dry_run=False, db=db)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)


if __name__ == "__main__":
    unittest.main()
