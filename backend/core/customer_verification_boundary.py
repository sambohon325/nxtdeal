"""Fail closed at HTTP entry for features backed only by simulated identity.

Legacy promoted tokens must not bypass this boundary. Keep core simulation tests
available, but do not expose their authority through public customer routes until
provider delivery/provenance, session expiry and revocation are implemented.
"""
from starlette.responses import JSONResponse


class CustomerVerificationBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "").rstrip("/")
        protected = any(path == root or path.startswith(root + "/")
                        for root in ("/public/verify", "/public/garage", "/public/retail"))
        if scope["type"] == "http" and scope.get("method") != "OPTIONS" and protected:
            response = JSONResponse(
                {"error": "Customer verification is not available yet. Please contact the dealership.",
                 "reason": "provider_unavailable"},
                status_code=503, headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
