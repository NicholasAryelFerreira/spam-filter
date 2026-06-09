from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    ms_tenant_id: str
    ms_client_id: str
    ms_client_secret: str
    ms_refresh_token: str
    mailbox_user_id: str
    graph_notification_url: str
    graph_client_state: str
    database_path: str
    admin_token: str
    environment: str
    inbox_confidence_threshold: float
    delete_confidence_threshold: float
    provider_allowlist_path: str

    @property
    def uses_delegated_auth(self) -> bool:
        return bool(self.ms_refresh_token)

    @property
    def graph_user_path(self) -> str:
        if self.uses_delegated_auth and not self.mailbox_user_id:
            return "/me"
        if not self.mailbox_user_id:
            raise ValueError("MAILBOX_USER_ID is required for app-only Microsoft Graph auth.")
        return f"/users/{self.mailbox_user_id}"

    @property
    def graph_subscription_resource(self) -> str:
        if self.uses_delegated_auth and not self.mailbox_user_id:
            return "me/messages"
        if not self.mailbox_user_id:
            raise ValueError("MAILBOX_USER_ID is required for app-only Microsoft Graph auth.")
        return f"users/{self.mailbox_user_id}/messages"

    def require_runtime_values(self) -> None:
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.ms_client_id:
            missing.append("MS_CLIENT_ID")
        if not self.graph_notification_url:
            missing.append("GRAPH_NOTIFICATION_URL")
        if not self.graph_client_state:
            missing.append("GRAPH_CLIENT_STATE")
        if not (self.ms_refresh_token or (self.ms_client_secret and self.mailbox_user_id)):
            missing.append("MS_REFRESH_TOKEN or MS_CLIENT_SECRET plus MAILBOX_USER_ID")
        if self.environment.lower() == "production" and not self.admin_token:
            missing.append("ADMIN_TOKEN")
        if missing:
            raise ValueError("Missing required settings: " + ", ".join(missing))


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
        ms_tenant_id=os.getenv("MS_TENANT_ID", "common"),
        ms_client_id=os.getenv("MS_CLIENT_ID", ""),
        ms_client_secret=os.getenv("MS_CLIENT_SECRET", ""),
        ms_refresh_token=os.getenv("MS_REFRESH_TOKEN", ""),
        mailbox_user_id=os.getenv("MAILBOX_USER_ID", ""),
        graph_notification_url=os.getenv("GRAPH_NOTIFICATION_URL", ""),
        graph_client_state=os.getenv("GRAPH_CLIENT_STATE", ""),
        database_path=os.getenv("DATABASE_PATH", "spam_filter.sqlite3"),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        environment=os.getenv("ENVIRONMENT", "development"),
        inbox_confidence_threshold=float(os.getenv("INBOX_CONFIDENCE_THRESHOLD", "0.92")),
        delete_confidence_threshold=float(os.getenv("DELETE_CONFIDENCE_THRESHOLD", "0.88")),
        provider_allowlist_path=os.getenv("PROVIDER_ALLOWLIST_PATH", "providers.json"),
    )

