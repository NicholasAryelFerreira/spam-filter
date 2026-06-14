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
        classification_prompt="Classify test email.",
    )


def message(message_id: str, sender: str, parent_folder_id: str = "deleted") -> EmailMessage:
    return EmailMessage(
        id=message_id,
        internet_message_id=f"<{message_id}@example.test>",
        parent_folder_id=parent_folder_id,
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
        self.messages = {}
        self.moved = []

    async def list_messages_in_folder(self, well_known_name: str, top: int = 25):
        self.folder = well_known_name
        self.top = top
        return [
            message("1", "spam1@example.com"),
            message("2", "spam2@example.com"),
            message("3", "spam1@example.com"),
        ][:top]

    async def list_all_messages_in_folder(self, well_known_name: str, page_size: int = 25, max_messages: int = 500):
        self.folder = well_known_name
        self.page_size = page_size
        self.max_messages = max_messages
        return [message("1", "spam1@example.com"), message("2", "spam2@example.com")][:max_messages]

    async def get_message(self, message_id: str):
        return self.messages[message_id]

    async def get_folder_id(self, well_known_name: str):
        return {
            "inbox": "inbox",
            "junkemail": "junk",
            "deleteditems": "deleted",
        }[well_known_name]

    async def move_message(self, message_id: str, destination: str):
        self.moved.append((message_id, destination))
        return {"id": message_id, "parentFolderId": destination}

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

    async def delete_subscription(self, subscription_id: str):
        self.deleted_subscription_id = subscription_id


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

            result = await service.block_all_deleted_senders(
                max_messages=50,
                page_size=10,
                note="bulk review",
            )

            self.assertEqual(graph.folder, "deleteditems")
            self.assertEqual(graph.max_messages, 50)
            self.assertEqual(graph.page_size, 10)
            self.assertEqual(result["reviewed_candidate_count"], 2)
            self.assertEqual(result["blocked_count"], 1)
            self.assertEqual(result["scanned_folder"], "deleteditems")
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

    async def test_blocked_sender_pattern_moves_non_junk_message_to_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = settings(str(Path(temp_dir) / "test.sqlite3"))
            db = Database(config.database_path)
            db.add_blocked_sender_pattern("skystoria", source="test", note="pattern")
            graph = FakeGraph()
            graph.messages["inbox-message"] = message(
                "inbox-message",
                "offer@123skystoria.online",
                parent_folder_id="inbox",
            )
            service = SpamFilterService(
                settings=config,
                db=db,
                graph=graph,
                classifier=FakeClassifier(),
                policy=DecisionPolicy(config, ProviderAllowlist.default()),
            )

            result = await service.process_message("inbox-message")

            self.assertEqual(result["status"], "processed")
            self.assertEqual(result["decision"]["action"], "move_to_deleted")
            self.assertEqual(graph.moved, [("inbox-message", "deleted")])
            self.assertTrue(db.is_processed("inbox-message"))

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

    async def test_delete_known_subscriptions_removes_graph_and_local_records(self) -> None:
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

            result = await service.delete_known_subscriptions()

            self.assertEqual(result["deleted"], ["existing-subscription"])
            self.assertEqual(result["failed"], [])
            self.assertEqual(graph.deleted_subscription_id, "existing-subscription")
            self.assertEqual(db.subscriptions(), [])

    async def test_deleted_sender_candidates_can_hide_already_blocked_senders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = settings(str(Path(temp_dir) / "test.sqlite3"))
            db = Database(config.database_path)
            db.add_blocked_sender("spam1@example.com", source="test", note="already")
            graph = FakeGraph()
            service = SpamFilterService(
                settings=config,
                db=db,
                graph=graph,
                classifier=FakeClassifier(),
                policy=DecisionPolicy(config, ProviderAllowlist.default()),
            )

            candidates = await service.all_deleted_sender_candidates(
                max_messages=50,
                page_size=10,
                include_blocked=False,
            )

            self.assertEqual([candidate.sender_email for candidate in candidates], ["spam2@example.com"])

    async def test_rescan_all_junk_uses_paged_folder_scan(self) -> None:
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

            async def process_message(message_id: str):
                return {"status": "processed", "message_id": message_id}

            service.process_message = process_message
            result = await service.rescan_all_junk(max_messages=2, page_size=1)

            self.assertEqual(graph.folder, "junkemail")
            self.assertEqual(graph.page_size, 1)
            self.assertEqual(result["found_messages"], 2)
            self.assertEqual([item["message_id"] for item in result["processed_results"]], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
