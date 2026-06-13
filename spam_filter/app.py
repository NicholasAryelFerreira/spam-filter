from __future__ import annotations

from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from spam_filter.config import get_settings
from spam_filter.graph import GraphError
from spam_filter.models import BlockAllDeletedSendersRequest, BlockSendersRequest
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
    try:
        return await service.create_subscription()
    except GraphError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "graph_status_code": exc.status_code,
                "graph_response": exc.response_text,
            },
        ) from exc


@app.get("/admin/diagnostics", dependencies=[Depends(require_admin)])
async def diagnostics() -> dict:
    config = {
        "has_openai_api_key": bool(settings.openai_api_key),
        "has_ms_client_id": bool(settings.ms_client_id),
        "has_ms_client_secret": bool(settings.ms_client_secret),
        "has_ms_refresh_token": bool(settings.ms_refresh_token),
        "has_graph_notification_url": bool(settings.graph_notification_url),
        "has_graph_client_state": bool(settings.graph_client_state),
        "has_admin_token": bool(settings.admin_token),
        "ms_tenant_id": settings.ms_tenant_id,
        "graph_notification_url": settings.graph_notification_url,
    }
    graph = {"auth": "not_checked"}
    try:
        junk_id = await service.graph.get_folder_id("junkemail")
        graph = {"auth": "ok", "junk_folder_id_present": bool(junk_id)}
    except GraphError as exc:
        graph = {
            "auth": "failed",
            "message": str(exc),
            "graph_status_code": exc.status_code,
            "graph_response": exc.response_text,
        }
    except Exception as exc:
        graph = {"auth": "failed", "message": type(exc).__name__}
    return {"config": config, "graph": graph}


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


@app.post("/admin/deleted-senders/block-all", dependencies=[Depends(require_admin)])
async def block_all_deleted_senders(request: BlockAllDeletedSendersRequest) -> dict:
    if not request.confirm_reviewed_deleted_items:
        raise HTTPException(
            status_code=400,
            detail="Set confirm_reviewed_deleted_items=true after reviewing Deleted Items candidates.",
        )
    return await service.block_all_deleted_senders(top=request.top, note=request.note)


@app.get("/admin/blocked-senders", dependencies=[Depends(require_admin)])
def list_blocked_senders() -> list[dict]:
    return service.db.list_blocked_senders()


@app.delete("/admin/blocked-senders/{sender_email}", dependencies=[Depends(require_admin)])
def unblock_sender(sender_email: str) -> dict:
    service.db.remove_blocked_sender(sender_email)
    return {"removed": sender_email.lower()}
