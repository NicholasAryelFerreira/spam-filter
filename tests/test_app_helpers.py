from __future__ import annotations

import unittest

from spam_filter.app import _extract_message_id


class AppHelperTests(unittest.TestCase):
    def test_extracts_message_id_from_resource_data(self) -> None:
        self.assertEqual(
            _extract_message_id({"resourceData": {"id": "message-123"}}),
            "message-123",
        )

    def test_extracts_message_id_from_resource_path(self) -> None:
        self.assertEqual(
            _extract_message_id({"resource": "me/messages/message-456"}),
            "message-456",
        )

    def test_missing_message_id_returns_none(self) -> None:
        self.assertIsNone(_extract_message_id({"resource": "me/mailFolders/inbox"}))


if __name__ == "__main__":
    unittest.main()
