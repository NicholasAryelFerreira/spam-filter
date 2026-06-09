from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Classification = Literal["legit_login_code", "junk_keep", "spam_harmful"]
Action = Literal["move_to_inbox", "keep_in_junk", "move_to_deleted"]


@dataclass(frozen=True)
class EmailMessage:
    id: str
    internet_message_id: str | None
    parent_folder_id: str | None
    sender_email: str
    sender_name: str
    subject: str
    received_at: str | None
    body_preview: str
    body_text: str
    has_attachments: bool
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassificationDecision:
    classification: Classification
    confidence: float
    reason_codes: list[str]
    safe_summary: str
    recommended_action: Action


@dataclass(frozen=True)
class FinalDecision:
    classification: Classification
    confidence: float
    action: Action
    reason: str
    model: str


class DeletedSenderSample(BaseModel):
    message_id: str
    subject: str
    received_at: str | None = None


class DeletedSenderCandidate(BaseModel):
    sender_email: str
    sender_name: str = ""
    message_count: int
    already_blocked: bool
    samples: list[DeletedSenderSample]


class BlockSendersRequest(BaseModel):
    senders: list[str] = Field(min_length=1)
    confirm_reviewed_deleted_items: bool
    note: str = ""
