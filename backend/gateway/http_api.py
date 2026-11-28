"""Localhost hook API. Dedicated token; does not go through session/JWT/RBAC."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.gateway.hook import handle_event
from backend.gateway.token import PATH, authorize_gateway_request, install_token_redact_filter

router = APIRouter()
install_token_redact_filter()


@router.post(PATH)
async def pre_tool(request: Request):
    denied = authorize_gateway_request(request)
    if denied is not None:
        return denied
    try:
        event = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "invalid JSON"})
    if not isinstance(event, dict):
        return JSONResponse(status_code=400, content={"detail": "invalid JSON"})
    fmt = "cursor" if (request.headers.get("X-Hermes-Hook-Format") or "").strip() == "cursor" else None
    return handle_event(event, fmt=fmt)
