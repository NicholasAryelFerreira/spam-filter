from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from spam_filter.config import Settings
from spam_filter.models import EmailMessage

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


class GraphClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=UTC)
        self._folder_cache: dict[str, str] = {}

    async def get_access_token(self) -> str:
        now = datetime.now(UTC)
        if self._access_token and now < self._token_expires_at - timedelta(minutes=5):
            return self._access_token

        token_url = (
            f"https://login.microsoftonline.com/{self.settings.ms_tenant_id}"
            "/oauth2/v2.0/token"
        )
        if self.settings.ms_refresh_token:
            data = {
                "client_id": self.settings.ms_client_id,
                "client_secret": self.settings.ms_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.settings.ms_refresh_token,
                "scope": "offline_access https://graph.microsoft.com/Mail.ReadWrite",
            }
        else:
            data = {
                "client_id": self.settings.ms_client_id,
                "client_secret": self.settings.ms_client_secret,
                "grant_type": "client_credentials",
                "scope": "https://graph.microsoft.com/.default",
            }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(token_url, data=data)
        if response.status_code >= 400:
            raise GraphError(f"Microsoft token request failed with HTTP {response.status_code}.")
        payload = response.json()
        self._access_token = payload["access_token"]
        self._token_expires_at = now + timedelta(seconds=int(payload.get("expires_in", 3600)))
        return self._access_token

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = await self.get_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{GRAPH_BASE_URL}{path}",
                headers=headers,
                **kwargs,
            )
        if response.status_code >= 400:
            raise GraphError(f"Microsoft Graph {method} {path} failed with HTTP {response.status_code}.")
        if response.status_code == 204:
            return None
        return response.json()

    async def get_folder_id(self, well_known_name: str) -> str:
        if well_known_name not in self._folder_cache:
            payload = await self.request("GET", f"{self.settings.graph_user_path}/mailFolders/{well_known_name}")
            self._folder_cache[well_known_name] = payload["id"]
        return self._folder_cache[well_known_name]

    async def get_message(self, message_id: str) -> EmailMessage:
        select = ",".join(
            [
                "id",
                "internetMessageId",
                "parentFolderId",
                "subject",
                "receivedDateTime",
                "bodyPreview",
                "body",
                "from",
                "sender",
                "hasAttachments",
                "internetMessageHeaders",
            ]
        )
        payload = await self.request(
            "GET",
            f"{self.settings.graph_user_path}/messages/{quote(message_id)}",
            params={"$select": select},
        )
        return self._message_from_payload(payload)

    async def list_messages_in_folder(self, well_known_name: str, top: int = 25) -> list[EmailMessage]:
        select = ",".join(
            [
                "id",
                "internetMessageId",
                "parentFolderId",
                "subject",
                "receivedDateTime",
                "bodyPreview",
                "body",
                "from",
                "sender",
                "hasAttachments",
            ]
        )
        payload = await self.request(
            "GET",
            f"{self.settings.graph_user_path}/mailFolders/{well_known_name}/messages",
            params={
                "$top": str(top),
                "$orderby": "receivedDateTime desc",
                "$select": select,
            },
        )
        return [self._message_from_payload(item) for item in payload.get("value", [])]

    async def move_message(self, message_id: str, destination: str) -> dict:
        return await self.request(
            "POST",
            f"{self.settings.graph_user_path}/messages/{quote(message_id)}/move",
            json={"destinationId": destination},
            headers={"Content-Type": "application/json"},
        )

    async def create_subscription(self) -> dict:
        expires_at = datetime.now(UTC) + timedelta(days=5)
        payload = await self.request(
            "POST",
            "/subscriptions",
            json={
                "changeType": "created",
                "notificationUrl": self.settings.graph_notification_url,
                "resource": self.settings.graph_subscription_resource,
                "expirationDateTime": expires_at.isoformat().replace("+00:00", "Z"),
                "clientState": self.settings.graph_client_state,
            },
            headers={"Content-Type": "application/json"},
        )
        return payload

    async def renew_subscription(self, subscription_id: str) -> dict:
        expires_at = datetime.now(UTC) + timedelta(days=5)
        payload = await self.request(
            "PATCH",
            f"/subscriptions/{quote(subscription_id)}",
            json={"expirationDateTime": expires_at.isoformat().replace("+00:00", "Z")},
            headers={"Content-Type": "application/json"},
        )
        return payload

    @staticmethod
    def _message_from_payload(payload: dict) -> EmailMessage:
        sender = payload.get("from") or payload.get("sender") or {}
        email_address = sender.get("emailAddress") or {}
        body = payload.get("body") or {}
        headers = {
            item.get("name", ""): item.get("value", "")
            for item in payload.get("internetMessageHeaders", []) or []
            if item.get("name")
        }
        return EmailMessage(
            id=payload["id"],
            internet_message_id=payload.get("internetMessageId"),
            parent_folder_id=payload.get("parentFolderId"),
            sender_email=(email_address.get("address") or "").strip().lower(),
            sender_name=email_address.get("name") or "",
            subject=payload.get("subject") or "",
            received_at=payload.get("receivedDateTime"),
            body_preview=payload.get("bodyPreview") or "",
            body_text=body.get("content") or "",
            has_attachments=bool(payload.get("hasAttachments")),
            headers=headers,
        )
