from __future__ import annotations

from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from spam_filter.config import get_settings
from spam_filter.models import BlockSendersRequest
from spam_filter.service import SpamFilterService

settings = get_settings()
service = SpamFilterService.create(settings)
app = FastAPI(title="Outlook AI Spam Filter", version="0.1.0")


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")
    if settings.environment.lower() == "production" and not settings.admin_token:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN is required in production.")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.openai_model,
        "subscriptions": service.db.subscriptions(),
    }


@app.post("/webhooks/graph")
async def graph_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    validation_token: str | None = Query(default=None, alias="validationToken"),
):
    if validation_token:
        return PlainTextResponse(validation_token)

    payload = await request.json()
    for notification in payload.get("value", []):
        if notification.get("clientState") != settings.graph_client_state:
            raise HTTPException(status_code=401, detail="Invalid Microsoft Graph clientState.")
        message_id = _extract_message_id(notification)
        if message_id:
            background_tasks.add_task(service.process_message, message_id)
    return {"accepted": True}


def _extract_message_id(notification: dict) -> str | None:
    resource_data = notification.get("resourceData") or {}
    if resource_data.get("id"):
        return resource_data["id"]

    resource = notification.get("resource") or ""
    marker = "/messages/"
    if marker in resource:
        return resource.rsplit(marker, 1)[-1]
    return None


@app.post("/admin/subscriptions", dependencies=[Depends(require_admin)])
async def create_subscription() -> dict:
    return await service.create_subscription()


@app.post("/admin/subscriptions/renew", dependencies=[Depends(require_admin)])
async def renew_subscriptions() -> list[dict]:
    return await service.renew_known_subscriptions()


@app.post("/admin/rescan-junk", dependencies=[Depends(require_admin)])
async def rescan_junk(top: int = 25) -> list[dict]:
    return await service.rescan_junk(top=top)


@app.get("/admin/decisions", dependencies=[Depends(require_admin)])
def recent_decisions(limit: int = 50) -> list[dict]:
    return service.db.recent_decisions(limit=limit)


@app.get("/admin/deleted-senders/candidates", dependencies=[Depends(require_admin)])
async def deleted_sender_candidates(top: int = 50):
    return await service.deleted_sender_candidates(top=top)


@app.post("/admin/deleted-senders/block", dependencies=[Depends(require_admin)])
def block_deleted_senders(request: BlockSendersRequest) -> list[dict]:
    if not request.confirm_reviewed_deleted_items:
        raise HTTPException(
            status_code=400,
            detail="Set confirm_reviewed_deleted_items=true after reviewing Deleted Items candidates.",
        )
    return service.block_reviewed_senders(request.senders, note=request.note)


@app.get("/admin/blocked-senders", dependencies=[Depends(require_admin)])
def list_blocked_senders() -> list[dict]:
    return service.db.list_blocked_senders()


@app.delete("/admin/blocked-senders/{sender_email}", dependencies=[Depends(require_admin)])
def unblock_sender(sender_email: str) -> dict:
    service.db.remove_blocked_sender(sender_email)
    return {"removed": sender_email.lower()}
