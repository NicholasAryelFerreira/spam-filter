from __future__ import annotations

import unittest

from spam_filter.config import Settings
from spam_filter.graph import GraphClient


def settings() -> Settings:
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
        database_path=":memory:",
        admin_token="admin",
        environment="test",
        inbox_confidence_threshold=0.92,
        delete_confidence_threshold=0.88,
        provider_allowlist_path="providers.json",
        classification_prompt="Classify test email.",
    )


def payload(message_id: str) -> dict:
    return {
        "id": message_id,
        "internetMessageId": f"<{message_id}@example.test>",
        "parentFolderId": "junk",
        "subject": "Sample",
        "receivedDateTime": "2026-06-13T12:00:00Z",
        "bodyPreview": "",
        "body": {"content": ""},
        "from": {"emailAddress": {"address": "sender@example.com", "name": "Sender"}},
        "hasAttachments": False,
    }


class FakePagedGraphClient(GraphClient):
    def __init__(self) -> None:
        super().__init__(settings())
        self.calls: list[tuple[str, str, dict | None]] = []

    async def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs.get("params")))
        if len(self.calls) == 1:
            return {
                "value": [payload("1"), payload("2")],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/mailFolders/junkemail/messages?page=2",
            }
        return {"value": [payload("3")]}


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_all_messages_in_folder_follows_next_link(self) -> None:
        graph = FakePagedGraphClient()

        messages = await graph.list_all_messages_in_folder("junkemail", page_size=2, max_messages=10)

        self.assertEqual([message.id for message in messages], ["1", "2", "3"])
        self.assertEqual(len(graph.calls), 2)
        self.assertIsNone(graph.calls[1][2])

    async def test_list_all_messages_in_folder_honors_max_messages(self) -> None:
        graph = FakePagedGraphClient()

        messages = await graph.list_all_messages_in_folder("junkemail", page_size=2, max_messages=2)

        self.assertEqual([message.id for message in messages], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
