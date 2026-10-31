"""Stateless MCP Streamable HTTP, JSON responses, no SSE/session state.

Supports protocol 2025-03-26 and 2025-06-18. Employee bearer authentication
is required; provider-hosted OAuth onboarding is a separate deployment concern.
"""
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import ValidationError

from api.routers.agent_fabric import employee, Invocation
from core import agent_fabric as fabric
from core.cors_policy import DEALER_WEB_ORIGINS
from core import agent_oauth as oauth
from api.deps import _bearer_token

router = APIRouter(prefix="/agent-fabric/mcp", tags=["Department MCP"])
VERSIONS = {"2025-03-26", "2025-06-18"}
TOOLS = [
    {"name": "nxtdeal_catalog", "description": "Read authorized department definitions and capability readiness.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "nxtdeal_invoke", "description": "Read a capability or prepare an action. Actions never execute in this call.",
     "inputSchema": Invocation.model_json_schema()},
    {"name": "nxtdeal_proposals", "description": "Read your action review queue. Approval and execution happen in NXTDeal.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


def mcp_employee(authorization: str | None = Header(None)):
    token = _bearer_token(authorization)
    actor = oauth.verify(token)
    if actor:
        return actor
    try:
        return employee(authorization)
    except HTTPException as exc:
        raise HTTPException(401, "Connect your NXTDeal employee account", headers={
            "WWW-Authenticate": f'Bearer resource_metadata="{oauth.issuer()}/.well-known/oauth-protected-resource/agent-fabric/mcp"',
            "Cache-Control": "no-store"}) from exc


def origin(request):
    value = request.headers.get("origin")
    if value and value not in DEALER_WEB_ORIGINS:
        raise HTTPException(403, "Origin not allowed")


@router.get("")
def stream(request: Request, actor=Depends(mcp_employee)):
    origin(request)
    return Response(status_code=405, headers={"Allow": "POST"})


@router.post("")
async def rpc(request: Request, actor=Depends(mcp_employee)):
    origin(request)
    version = request.headers.get("mcp-protocol-version", "2025-03-26")
    if version not in VERSIONS:
        raise HTTPException(400, "Unsupported MCP protocol version")
    accept = request.headers.get("accept", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        raise HTTPException(406, "Accept application/json and text/event-stream")
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(415, "JSON required")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > 65536:
            raise HTTPException(413, "Request too large")
    try:
        message = json.loads(raw)
    except ValueError:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    method = message["method"]
    if "id" not in message:
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return Response(status_code=202)
        raise HTTPException(400, "Unsupported notification")
    request_id = message["id"]
    if isinstance(request_id, (dict, list, bool)):
        raise HTTPException(400, "Invalid request ID")
    params = message.get("params", {})
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params"}}
    if method == "initialize":
        requested = params.get("protocolVersion")
        result = {"protocolVersion": requested if requested in VERSIONS else "2025-06-18",
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "nxtdeal", "version": "1.0"},
                  "instructions": "Use canonical department capabilities. Prepare actions for human review in NXTDeal."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{**tool, "securitySchemes": [{"type": "oauth2", "scopes": ["nxtdeal:read", "nxtdeal:propose"] if tool["name"] == "nxtdeal_invoke" else ["nxtdeal:read"]}],
                             "annotations": {"readOnlyHint": tool["name"] != "nxtdeal_invoke", "destructiveHint": False, "openWorldHint": False}}
                            for tool in TOOLS]}
    elif method == "tools/call":
        try:
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            if params.get("name") == "nxtdeal_invoke":
                args = Invocation.model_validate(arguments)
                capability = fabric.CAPABILITIES.get(args.capability)
                if (actor.get("principal") == "oauth" and capability and capability.kind == "ACTION"
                        and "nxtdeal:propose" not in actor.get("oauth_scopes", [])):
                    return {"jsonrpc": "2.0", "id": request_id, "result": {
                        "content": [{"type": "text", "text": "Reconnect with proposal permission to prepare this action."}], "isError": True,
                        "_meta": {"mcp/www_authenticate": [f'Bearer error="insufficient_scope", scope="nxtdeal:read nxtdeal:propose", resource_metadata="{oauth.issuer()}/.well-known/oauth-protected-resource/agent-fabric/mcp"']}}}
                output = fabric.invoke(actor, args.department, args.capability, args.input, args.provider, args.idempotency_key)
            elif params.get("name") == "nxtdeal_catalog" and not arguments:
                output = fabric.catalog(actor)
            elif params.get("name") == "nxtdeal_proposals" and not arguments:
                output = {"proposals": [p for p in fabric.proposals(actor) if not actor.get("oauth_departments") or p["department"] in actor["oauth_departments"]]}
            else:
                raise ValueError("Unknown tool or invalid arguments")
            result = {"content": [{"type": "text", "text": json.dumps(output)}], "isError": False}
        except (ValueError, PermissionError, ValidationError):
            result = {"content": [{"type": "text", "text": "Request rejected by NXTDeal permissions or input contract"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
