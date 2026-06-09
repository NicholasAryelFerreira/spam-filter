from __future__ import annotations

import json
from dataclasses import asdict

from spam_filter.config import Settings
from spam_filter.models import ClassificationDecision, EmailMessage, FinalDecision
from spam_filter.providers import ProviderAllowlist


CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["legit_login_code", "junk_keep", "spam_harmful"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason_codes": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "safe_summary": {"type": "string", "maxLength": 280},
        "recommended_action": {
            "type": "string",
            "enum": ["move_to_inbox", "keep_in_junk", "move_to_deleted"],
        },
    },
    "required": [
        "classification",
        "confidence",
        "reason_codes",
        "safe_summary",
        "recommended_action",
    ],
}


class OpenAIEmailClassifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def classify(self, message: EmailMessage) -> ClassificationDecision:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        prompt = {
            "sender_email": message.sender_email,
            "sender_name": message.sender_name,
            "subject": message.subject,
            "received_at": message.received_at,
            "body_preview": message.body_preview[:1000],
            "body_text": message.body_text[:6000],
            "has_attachments": message.has_attachments,
            "headers": {
                key: value[:600]
                for key, value in message.headers.items()
                if key.lower() in {"authentication-results", "arc-authentication-results", "from", "reply-to"}
            },
        }

        response = await client.responses.create(
            model=self.settings.openai_model,
            instructions=(
                "Classify a message that arrived in Outlook Junk Email. "
                "Move to Inbox only for legitimate provider login-code or verification-code emails. "
                "Use spam_harmful for clear phishing, malware, extortion, credential theft, or scams. "
                "If uncertain, choose junk_keep. Return only the requested structured JSON."
            ),
            input=json.dumps(prompt, ensure_ascii=True),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "junk_email_classification",
                    "strict": True,
                    "schema": CLASSIFICATION_SCHEMA,
                }
            },
        )
        raw = response.output_text
        parsed = json.loads(raw)
        return ClassificationDecision(
            classification=parsed["classification"],
            confidence=float(parsed["confidence"]),
            reason_codes=list(parsed["reason_codes"]),
            safe_summary=parsed["safe_summary"],
            recommended_action=parsed["recommended_action"],
        )


class DecisionPolicy:
    def __init__(self, settings: Settings, providers: ProviderAllowlist) -> None:
        self.settings = settings
        self.providers = providers

    def apply(
        self,
        message: EmailMessage,
        model_decision: ClassificationDecision,
        is_blocked_sender: bool = False,
    ) -> FinalDecision:
        if is_blocked_sender:
            return FinalDecision(
                classification="spam_harmful",
                confidence=1.0,
                action="move_to_deleted",
                reason="Sender was explicitly blocked after Deleted Items review.",
                model=self.settings.openai_model,
            )

        if (
            model_decision.classification == "legit_login_code"
            and model_decision.confidence >= self.settings.inbox_confidence_threshold
            and self.providers.is_allowed_login_code(message)
        ):
            return FinalDecision(
                classification="legit_login_code",
                confidence=model_decision.confidence,
                action="move_to_inbox",
                reason=model_decision.safe_summary,
                model=self.settings.openai_model,
            )

        if (
            model_decision.classification == "spam_harmful"
            and model_decision.confidence >= self.settings.delete_confidence_threshold
        ):
            return FinalDecision(
                classification="spam_harmful",
                confidence=model_decision.confidence,
                action="move_to_deleted",
                reason=model_decision.safe_summary,
                model=self.settings.openai_model,
            )

        return FinalDecision(
            classification="junk_keep",
            confidence=model_decision.confidence,
            action="keep_in_junk",
            reason=(
                "Left in Junk Email because the message was not a verified login-code rescue "
                "and was not confidently harmful."
            ),
            model=self.settings.openai_model,
        )


def fallback_junk_decision(settings: Settings, reason: str) -> FinalDecision:
    return FinalDecision(
        classification="junk_keep",
        confidence=0.0,
        action="keep_in_junk",
        reason=reason,
        model=settings.openai_model,
    )


def decision_as_safe_dict(decision: FinalDecision) -> dict:
    return asdict(decision)
