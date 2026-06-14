from __future__ import annotations

import hashlib

from spam_filter.classifier import (
    DecisionPolicy,
    OpenAIEmailClassifier,
    fallback_junk_decision,
)
from spam_filter.config import Settings
from spam_filter.database import Database
from spam_filter.graph import GraphClient
from spam_filter.models import DeletedSenderCandidate, DeletedSenderSample, FinalDecision
from spam_filter.providers import ProviderAllowlist


class SpamFilterService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        graph: GraphClient,
        classifier: OpenAIEmailClassifier,
        policy: DecisionPolicy,
    ) -> None:
        self.settings = settings
        self.db = db
        self.graph = graph
        self.classifier = classifier
        self.policy = policy

    @classmethod
    def create(cls, settings: Settings) -> "SpamFilterService":
        db = Database(settings.database_path)
        providers = ProviderAllowlist.from_file(settings.provider_allowlist_path)
        return cls(
            settings=settings,
            db=db,
            graph=GraphClient(settings),
            classifier=OpenAIEmailClassifier(settings),
            policy=DecisionPolicy(settings, providers),
        )

    async def process_message(self, message_id: str) -> dict:
        if self.db.is_processed(message_id):
            return {"status": "already_processed", "message_id": message_id}

        message = await self.graph.get_message(message_id)
        blocked_pattern = self.db.matching_blocked_sender_pattern(message.sender_email)
        if self.db.is_blocked_sender(message.sender_email) or blocked_pattern:
            final_decision = self.policy.apply(
                message=message,
                model_decision=fallback_junk_decision(self.settings, "Blocked sender."),
                is_blocked_sender=True,
            )
            if blocked_pattern:
                final_decision = FinalDecision(
                    classification=final_decision.classification,
                    confidence=final_decision.confidence,
                    action=final_decision.action,
                    reason=(
                        "Sender email matched blocked pattern "
                        f"'{blocked_pattern['pattern']}'."
                    ),
                    model=final_decision.model,
                )
        else:
            junk_folder_id = await self.graph.get_folder_id("junkemail")
            if message.parent_folder_id != junk_folder_id:
                return {"status": "ignored_not_junk", "message_id": message_id}

            try:
                model_decision = await self.classifier.classify(message)
                final_decision = self.policy.apply(message, model_decision)
            except Exception as exc:  # Keep mail in Junk on any classifier failure.
                final_decision = fallback_junk_decision(
                    self.settings,
                    f"Classifier failed safely: {type(exc).__name__}.",
                )

        await self._apply_action(message, final_decision)
        subject_hash = hashlib.sha256(message.subject.encode("utf-8")).hexdigest()
        self.db.record_decision(message.id, message.sender_email, subject_hash, final_decision)
        self.db.record_processed(
            message.id,
            message.internet_message_id,
            message.sender_email,
            final_decision,
        )
        return {
            "status": "processed",
            "message_id": message.id,
            "sender_email": message.sender_email,
            "decision": {
                "classification": final_decision.classification,
                "confidence": final_decision.confidence,
                "action": final_decision.action,
                "reason": final_decision.reason,
            },
        }

    async def rescan_junk(self, top: int = 25) -> list[dict]:
        messages = await self.graph.list_messages_in_folder("junkemail", top=top)
        results = []
        for message in messages:
            results.append(await self.process_message(message.id))
        return results

    async def rescan_all_junk(self, max_messages: int = 500, page_size: int = 25) -> dict:
        messages = await self.graph.list_all_messages_in_folder(
            "junkemail",
            page_size=page_size,
            max_messages=max_messages,
        )
        results = []
        for message in messages:
            results.append(await self.process_message(message.id))
        return {
            "requested_max_messages": max_messages,
            "found_messages": len(messages),
            "processed_results": results,
        }

    async def create_subscription(self) -> dict:
        payload = await self.graph.create_subscription()
        self.db.upsert_subscription(
            payload["id"],
            payload.get("resource", self.settings.graph_subscription_resource),
            payload["expirationDateTime"],
        )
        return payload

    async def renew_known_subscriptions(self) -> list[dict]:
        renewed = []
        for subscription in self.db.subscriptions():
            try:
                payload = await self.graph.renew_subscription(subscription["subscription_id"])
            except Exception:
                payload = await self.graph.create_subscription()
            self.db.upsert_subscription(
                payload["id"],
                payload.get("resource", subscription["resource"]),
                payload["expirationDateTime"],
            )
            renewed.append(payload)
        return renewed

    async def ensure_subscription(self) -> dict:
        subscriptions = self.db.subscriptions()
        if not subscriptions:
            payload = await self.graph.create_subscription()
            self.db.upsert_subscription(
                payload["id"],
                payload.get("resource", self.settings.graph_subscription_resource),
                payload["expirationDateTime"],
            )
            return {"action": "created", "subscription": payload}

        renewed = await self.renew_known_subscriptions()
        return {"action": "renewed", "subscriptions": renewed}

    async def delete_known_subscriptions(self) -> dict:
        deleted = []
        failed = []
        for subscription in self.db.subscriptions():
            subscription_id = subscription["subscription_id"]
            try:
                await self.graph.delete_subscription(subscription_id)
                deleted.append(subscription_id)
            except Exception as exc:
                failed.append({"subscription_id": subscription_id, "error": type(exc).__name__})
            finally:
                self.db.remove_subscription(subscription_id)
        return {"deleted": deleted, "failed": failed}

    async def deleted_sender_candidates(
        self,
        top: int = 50,
        include_blocked: bool = True,
    ) -> list[DeletedSenderCandidate]:
        messages = await self.graph.list_messages_in_folder("deleteditems", top=top)
        return self._group_deleted_sender_candidates(messages, include_blocked=include_blocked)

    async def all_deleted_sender_candidates(
        self,
        max_messages: int = 500,
        page_size: int = 25,
        include_blocked: bool = True,
    ) -> list[DeletedSenderCandidate]:
        messages = await self.graph.list_all_messages_in_folder(
            "deleteditems",
            page_size=page_size,
            max_messages=max_messages,
        )
        return self._group_deleted_sender_candidates(messages, include_blocked=include_blocked)

    def _group_deleted_sender_candidates(
        self,
        messages,
        include_blocked: bool = True,
    ) -> list[DeletedSenderCandidate]:
        grouped: dict[str, DeletedSenderCandidate] = {}
        for message in messages:
            sender = message.sender_email
            if not sender:
                continue
            already_blocked = self.db.is_blocked_sender(sender) or bool(
                self.db.matching_blocked_sender_pattern(sender)
            )
            if already_blocked and not include_blocked:
                continue
            sample = DeletedSenderSample(
                message_id=message.id,
                subject=message.subject,
                received_at=message.received_at,
            )
            if sender not in grouped:
                grouped[sender] = DeletedSenderCandidate(
                    sender_email=sender,
                    sender_name=message.sender_name,
                    message_count=1,
                    already_blocked=already_blocked,
                    samples=[sample],
                )
                continue

            candidate = grouped[sender]
            candidate.message_count += 1
            if len(candidate.samples) < 3:
                candidate.samples.append(sample)

        return sorted(grouped.values(), key=lambda item: item.message_count, reverse=True)

    def block_reviewed_senders(self, senders: list[str], note: str = "") -> list[dict]:
        for sender in senders:
            self.db.add_blocked_sender(sender, source="deleted_items_review", note=note)
        return self.db.list_blocked_senders()

    def block_sender_patterns(self, patterns: list[str], note: str = "") -> list[dict]:
        for pattern in patterns:
            self.db.add_blocked_sender_pattern(pattern, source="manual_pattern_review", note=note)
        return self.db.list_blocked_sender_patterns()

    async def block_all_deleted_senders(
        self,
        max_messages: int = 500,
        page_size: int = 25,
        note: str = "",
    ) -> dict:
        candidates = await self.all_deleted_sender_candidates(
            max_messages=max_messages,
            page_size=page_size,
        )
        senders = [
            candidate.sender_email
            for candidate in candidates
            if candidate.sender_email and not candidate.already_blocked
        ]
        for sender in senders:
            self.db.add_blocked_sender(sender, source="deleted_items_bulk_review", note=note)
        return {
            "blocked_count": len(senders),
            "reviewed_candidate_count": len(candidates),
            "scanned_folder": "deleteditems",
            "requested_max_messages": max_messages,
            "blocked_senders": self.db.list_blocked_senders(),
        }

    async def _apply_action(self, message, decision: FinalDecision) -> None:
        if decision.action == "move_to_inbox":
            inbox_folder_id = await self.graph.get_folder_id("inbox")
            if message.parent_folder_id != inbox_folder_id:
                await self.graph.move_message(message.id, inbox_folder_id)
        elif decision.action == "move_to_deleted":
            deleted_folder_id = await self.graph.get_folder_id("deleteditems")
            if message.parent_folder_id != deleted_folder_id:
                await self.graph.move_message(message.id, deleted_folder_id)
