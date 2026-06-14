from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spam_filter.database import Database
from spam_filter.models import FinalDecision


class DatabaseTests(unittest.TestCase):
    def test_blocked_sender_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(str(Path(temp_dir) / "test.sqlite3"))
            self.assertFalse(db.is_blocked_sender("spam@example.com"))
            db.add_blocked_sender("Spam@Example.com", source="test", note="reviewed")
            self.assertTrue(db.is_blocked_sender("spam@example.com"))
            records = db.list_blocked_senders()
            self.assertEqual(records[0]["sender_email"], "spam@example.com")
            db.remove_blocked_sender("spam@example.com")
            self.assertFalse(db.is_blocked_sender("spam@example.com"))

    def test_blocked_sender_pattern_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(str(Path(temp_dir) / "test.sqlite3"))
            self.assertIsNone(db.matching_blocked_sender_pattern("spam@123skystoria.online"))
            db.add_blocked_sender_pattern("SkyStoria", source="test", note="pattern")
            match = db.matching_blocked_sender_pattern("spam@123skystoria.online")
            self.assertIsNotNone(match)
            self.assertEqual(match["pattern"], "skystoria")
            records = db.list_blocked_sender_patterns()
            self.assertEqual(records[0]["pattern"], "skystoria")
            db.remove_blocked_sender_pattern("skystoria")
            self.assertIsNone(db.matching_blocked_sender_pattern("spam@123skystoria.online"))

    def test_processed_message_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(str(Path(temp_dir) / "test.sqlite3"))
            decision = FinalDecision(
                classification="junk_keep",
                confidence=0.0,
                action="keep_in_junk",
                reason="test",
                model="gpt-5.4-nano",
            )
            self.assertFalse(db.is_processed("message-1"))
            db.record_processed("message-1", "<m@example.test>", "sender@example.com", decision)
            self.assertTrue(db.is_processed("message-1"))

    def test_subscription_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(str(Path(temp_dir) / "test.sqlite3"))
            db.upsert_subscription("sub-1", "me/messages", "2026-06-18T12:00:00Z")
            self.assertEqual(len(db.subscriptions()), 1)
            db.remove_subscription("sub-1")
            self.assertEqual(db.subscriptions(), [])


if __name__ == "__main__":
    unittest.main()
