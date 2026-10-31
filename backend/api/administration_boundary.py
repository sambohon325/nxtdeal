"""Request-level system administration boundary, including direct URL access."""
from starlette.responses import JSONResponse
from api.deps import _authenticate
from core.administration_access import is_system_admin, requires_system_admin, system_admin_context


class AdministrationBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        payload, error = _authenticate(authorization) if authorization else (None, None)
        system = is_system_admin(payload) if not error else False
        token = system_admin_context.set(system)
        try:
            if requires_system_admin(scope["path"], scope["method"]) and not system:
                response = JSONResponse({"error": "NXTDeal system administrator access required",
                    "code": "system_admin_required"}, status_code=403 if payload else 401,
                    headers={"Cache-Control": "no-store"})
                return await response(scope, receive, send)
            return await self.app(scope, receive, send)
        finally:
            system_admin_context.reset(token)
