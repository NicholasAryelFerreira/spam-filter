from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spam_filter.classifier import DecisionPolicy
from spam_filter.config import Settings
from spam_filter.database import Database
from spam_filter.models import EmailMessage
from spam_filter.providers import ProviderAllowlist
from spam_filter.service import SpamFilterService


def settings(database_path: str) -> Settings:
    return Settings(
        openai_api_key="test",
        openai_model="gpt-5.4-nano",
        ms_tenant_id="consumers",
        ms_client_id="client",
        ms_client_secret="secret",
        ms_refresh_token="refresh",
        mailbox_user_id="",
        graph_notification_url="https://example.test/webhooks/graph",
        graph_client_state="state",
        database_path=database_path,
        admin_token="admin",
        environment="test",
        inbox_confidence_threshold=0.92,
        delete_confidence_threshold=0.88,
        provider_allowlist_path="providers.json",
    )


def message(message_id: str, sender: str) -> EmailMessage:
    return EmailMessage(
        id=message_id,
        internet_message_id=f"<{message_id}@example.test>",
        parent_folder_id="deleted",
        sender_email=sender,
        sender_name=sender,
        subject=f"Deleted sample {message_id}",
        received_at="2026-06-13T12:00:00Z",
        body_preview="",
        body_text="",
        has_attachments=False,
    )


class FakeGraph:
    def __init__(self) -> None:
        self.created = 0
        self.renewed = 0

    async def list_messages_in_folder(self, well_known_name: str, top: int = 25):
        self.folder = well_known_name
        self.top = top
        return [
            message("1", "spam1@example.com"),
            message("2", "spam2@example.com"),
            message("3", "spam1@example.com"),
        ][:top]

    async def create_subscription(self):
        self.created += 1
        return {
            "id": "created-subscription",
            "resource": "me/messages",
            "expirationDateTime": "2026-06-18T12:00:00Z",
        }

    async def renew_subscription(self, subscription_id: str):
        self.renewed += 1
        return {
            "id": subscription_id,
            "resource": "me/messages",
            "expirationDateTime": "2026-06-18T12:00:00Z",
        }


class FakeClassifier:
    pass


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_block_all_deleted_senders_blocks_unique_unblocked_senders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = settings(str(Path(temp_dir) / "test.sqlite3"))
            db = Database(config.database_path)
            db.add_blocked_sender("spam2@example.com", source="test", note="already")
            graph = FakeGraph()
            service = SpamFilterService(
                settings=config,
                db=db,
                graph=graph,
                classifier=FakeClassifier(),
                policy=DecisionPolicy(config, ProviderAllowlist.default()),
            )

            result = await service.block_all_deleted_senders(top=50, note="bulk review")

            self.assertEqual(graph.folder, "deleteditems")
            self.assertEqual(result["reviewed_candidate_count"], 2)
            self.assertEqual(result["blocked_count"], 1)
            self.assertTrue(db.is_blocked_sender("spam1@example.com"))
            self.assertTrue(db.is_blocked_sender("spam2@example.com"))

    async def test_ensure_subscription_creates_when_none_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = settings(str(Path(temp_dir) / "test.sqlite3"))
            db = Database(config.database_path)
            graph = FakeGraph()
            service = SpamFilterService(
                settings=config,
                db=db,
                graph=graph,
                classifier=FakeClassifier(),
                policy=DecisionPolicy(config, ProviderAllowlist.default()),
            )

            result = await service.ensure_subscription()

            self.assertEqual(result["action"], "created")
            self.assertEqual(graph.created, 1)
            self.assertEqual(len(db.subscriptions()), 1)

    async def test_ensure_subscription_renews_when_subscription_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = settings(str(Path(temp_dir) / "test.sqlite3"))
            db = Database(config.database_path)
            db.upsert_subscription("existing-subscription", "me/messages", "2026-06-14T12:00:00Z")
            graph = FakeGraph()
            service = SpamFilterService(
                settings=config,
                db=db,
                graph=graph,
                classifier=FakeClassifier(),
                policy=DecisionPolicy(config, ProviderAllowlist.default()),
            )

            result = await service.ensure_subscription()

            self.assertEqual(result["action"], "renewed")
            self.assertEqual(graph.renewed, 1)
            self.assertEqual(db.subscriptions()[0]["subscription_id"], "existing-subscription")


if __name__ == "__main__":
    unittest.main()
