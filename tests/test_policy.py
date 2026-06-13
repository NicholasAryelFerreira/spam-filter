from __future__ import annotations

import unittest

from spam_filter.classifier import DecisionPolicy
from spam_filter.config import Settings
from spam_filter.models import ClassificationDecision, EmailMessage
from spam_filter.providers import ProviderAllowlist


def settings() -> Settings:
    return Settings(
        openai_api_key="test",
        openai_model="gpt-5.4-nano",
        ms_tenant_id="common",
        ms_client_id="client",
        ms_client_secret="secret",
        ms_refresh_token="",
        mailbox_user_id="user@example.com",
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


def message(sender: str, subject: str, body: str, headers: dict[str, str] | None = None) -> EmailMessage:
    return EmailMessage(
        id="1",
        internet_message_id="<1@example.test>",
        parent_folder_id="junk",
        sender_email=sender,
        sender_name="Sender",
        subject=subject,
        received_at="2026-06-09T12:00:00Z",
        body_preview=body,
        body_text=body,
        has_attachments=False,
        headers=headers or {},
    )


class PolicyTests(unittest.TestCase):
    def test_legit_openai_code_can_move_to_inbox(self) -> None:
        policy = DecisionPolicy(settings(), ProviderAllowlist.default())
        decision = policy.apply(
            message(
                "noreply@openai.com",
                "Your OpenAI verification code",
                "Your login code is 123456.",
                {"Authentication-Results": "spf=pass dkim=pass dmarc=pass"},
            ),
            ClassificationDecision(
                classification="legit_login_code",
                confidence=0.96,
                reason_codes=["login_code"],
                safe_summary="Legitimate OpenAI login code.",
                recommended_action="move_to_inbox",
            ),
        )
        self.assertEqual(decision.action, "move_to_inbox")

    def test_legit_anthropic_code_from_provider_file_can_move_to_inbox(self) -> None:
        policy = DecisionPolicy(settings(), ProviderAllowlist.from_file("providers.json"))
        decision = policy.apply(
            message(
                "login@mail.anthropic.com",
                "Your Anthropic verification code",
                "Your sign in code is 123456.",
                {"Authentication-Results": "spf=pass dkim=pass dmarc=pass"},
            ),
            ClassificationDecision(
                classification="legit_login_code",
                confidence=0.96,
                reason_codes=["login_code"],
                safe_summary="Legitimate Anthropic login code.",
                recommended_action="move_to_inbox",
            ),
        )
        self.assertEqual(decision.action, "move_to_inbox")

    def test_non_provider_code_stays_in_junk_even_if_model_likes_it(self) -> None:
        policy = DecisionPolicy(settings(), ProviderAllowlist.default())
        decision = policy.apply(
            message("attacker@example.net", "OpenAI code", "Your login code is 123456."),
            ClassificationDecision(
                classification="legit_login_code",
                confidence=0.99,
                reason_codes=["login_code"],
                safe_summary="Looks like a code.",
                recommended_action="move_to_inbox",
            ),
        )
        self.assertEqual(decision.action, "keep_in_junk")

    def test_harmful_spam_moves_to_deleted_above_threshold(self) -> None:
        policy = DecisionPolicy(settings(), ProviderAllowlist.default())
        decision = policy.apply(
            message("scam@example.net", "Urgent password reset", "Click this suspicious link."),
            ClassificationDecision(
                classification="spam_harmful",
                confidence=0.91,
                reason_codes=["phishing"],
                safe_summary="Clear phishing.",
                recommended_action="move_to_deleted",
            ),
        )
        self.assertEqual(decision.action, "move_to_deleted")

    def test_uncertain_harm_stays_in_junk_below_threshold(self) -> None:
        policy = DecisionPolicy(settings(), ProviderAllowlist.default())
        decision = policy.apply(
            message("unknown@example.net", "Hello", "Please review this."),
            ClassificationDecision(
                classification="spam_harmful",
                confidence=0.50,
                reason_codes=["uncertain"],
                safe_summary="Unclear.",
                recommended_action="move_to_deleted",
            ),
        )
        self.assertEqual(decision.action, "keep_in_junk")

    def test_blocked_sender_moves_to_deleted_without_model_confidence(self) -> None:
        policy = DecisionPolicy(settings(), ProviderAllowlist.default())
        decision = policy.apply(
            message("blocked@example.net", "Anything", "Anything"),
            ClassificationDecision(
                classification="junk_keep",
                confidence=0.0,
                reason_codes=[],
                safe_summary="Fallback.",
                recommended_action="keep_in_junk",
            ),
            is_blocked_sender=True,
        )
        self.assertEqual(decision.action, "move_to_deleted")
        self.assertEqual(decision.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
