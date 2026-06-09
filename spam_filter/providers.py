from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from spam_filter.models import EmailMessage

CODE_PATTERN = re.compile(r"\b(?:\d{6,8}|[A-Z0-9]{6,10})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Provider:
    name: str
    domains: tuple[str, ...]
    login_code_terms: tuple[str, ...]


class ProviderAllowlist:
    def __init__(self, providers: list[Provider]) -> None:
        self.providers = providers

    @classmethod
    def from_file(cls, path: str) -> "ProviderAllowlist":
        file_path = Path(path)
        if not file_path.exists():
            return cls.default()
        data = json.loads(file_path.read_text(encoding="utf-8"))
        providers = [
            Provider(
                name=item["name"],
                domains=tuple(domain.lower() for domain in item.get("domains", [])),
                login_code_terms=tuple(term.lower() for term in item.get("login_code_terms", [])),
            )
            for item in data.get("providers", [])
        ]
        return cls(providers or cls.default().providers)

    @classmethod
    def default(cls) -> "ProviderAllowlist":
        return cls(
            [
                Provider(
                    name="OpenAI",
                    domains=("openai.com", "auth.openai.com", "mail.openai.com", "notifications.openai.com"),
                    login_code_terms=("code", "verification", "verify", "login", "sign in", "authentication"),
                )
            ]
        )

    def find_provider_for_sender(self, sender_email: str) -> Provider | None:
        domain = sender_email.rsplit("@", 1)[-1].lower()
        for provider in self.providers:
            if any(domain == allowed or domain.endswith(f".{allowed}") for allowed in provider.domains):
                return provider
        return None

    def is_allowed_login_code(self, message: EmailMessage) -> bool:
        provider = self.find_provider_for_sender(message.sender_email)
        if not provider:
            return False

        haystack = f"{message.subject}\n{message.body_preview}\n{message.body_text}".lower()
        has_term = any(term in haystack for term in provider.login_code_terms)
        has_code = bool(CODE_PATTERN.search(haystack))
        auth_ok = self._authentication_passes_if_present(message.headers)
        return has_term and has_code and auth_ok and not message.has_attachments

    @staticmethod
    def _authentication_passes_if_present(headers: dict[str, str]) -> bool:
        auth_results = " ".join(
            value.lower()
            for key, value in headers.items()
            if key.lower() in {"authentication-results", "arc-authentication-results"}
        )
        if not auth_results:
            return True
        failure_terms = ("spf=fail", "dkim=fail", "dmarc=fail", "spf=softfail")
        if any(term in auth_results for term in failure_terms):
            return False
        pass_terms = ("spf=pass", "dkim=pass", "dmarc=pass")
        return any(term in auth_results for term in pass_terms)

