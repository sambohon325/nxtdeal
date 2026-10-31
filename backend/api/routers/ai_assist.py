"""Inline AI Text-Assist router -- core/ai_assist.py's single generic text
transform (generate/rewrite/shorten/expand/retone/grammar) reused by every
text field across NXTDeal. See that module's own docstring for the "one
generic function, not twenty per-field wizards" reasoning and its honest
deterministic-fallback behavior.

Follows api/routers/communications_hub.py's own established pattern exactly: a
self-contained api/routers/<domain>.py module with its own APIRouter(),
importing the shared _authenticate helper from api/deps.py. Open to any
authenticated role (the ACL in core/ai_assist_api.py permits all six real
employee roles).
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.ai_assist_api import assist_text_api


router = APIRouter()


class AiAssistRequest(BaseModel):

    text: str = ""
    action: str
    tone: str | None = None
    context: str | None = None


@router.post("/ai-assist")
def ai_assist_route(request: AiAssistRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assist_text_api(
        payload["role"],
        request.text,
        request.action,
        tone=request.tone,
        context=request.context,
    )
