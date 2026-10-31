"""Read-only adapter to Chrono's published business API; never uploads dealer data.

Host and credential are deployment-owned, business is explicitly configured.
Saved reports keep their cutoffs; connection health is not forecast readiness.
"""
from datetime import datetime, timezone
import json
import os
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from core.secrets import get_secret


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def configuration():
    business = os.getenv("NXTDEAL_CHRONO_BUSINESS", "")
    token = get_secret("NXTDEAL_CHRONO_TOKEN")
    return {"status": "configured_unverified" if business and token else "needs_configuration",
            "endpoint": "https://api.chrono.technology", "business": business or None,
            "credential_configured": bool(token), "mode": "read_only",
            "missing": [name for name, value in (("NXTDEAL_CHRONO_BUSINESS", business), ("NXTDEAL_CHRONO_TOKEN", token)) if not value],
            "predictions": "Saved analyses only; no automatic forecast or data export"}


def fetch(path):
    # Fixed verified product hostname: no caller-controlled URLs or credential redirects.
    request = Request("https://api.chrono.technology" + path,
                      headers={"Authorization": "Bearer " + get_secret("NXTDEAL_CHRONO_TOKEN"), "Accept": "application/json"})
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576 or response.headers.get_content_type() != "application/json":
            raise ValueError("Invalid Chrono response")
        return json.loads(raw)


def read(actor, kind):
    if actor.get("role") not in {"ADMIN", "OPERATIONS"}:
        raise PermissionError("Company-level Chrono reads require an administrator or operations employee")
    config = configuration()
    if config["status"] != "configured_unverified":
        return {"status": "unavailable", "reason": "Chrono business and scoped API credential must be configured", "mode": "read_only"}
    business = config["business"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", business):
        return {"status": "unavailable", "reason": "Invalid configured Chrono business identifier"}
    if kind not in {"workspace-summary", "analysis-history"}:
        raise ValueError("Unsupported Chrono read")
    instant = datetime.now(timezone.utc).isoformat()
    query = {"as_of": instant, "known_at": instant}
    if kind == "analysis-history":
        query["limit"] = 20
    try:
        result = fetch("/v1/businesses/" + quote(business, safe="") + "/" + kind + "?" + urlencode(query))
        if not isinstance(result, dict) or result.get("business") != business:
            raise ValueError("Chrono scope mismatch")
        if kind == "analysis-history":
            if not isinstance(result.get("reports"), list) or len(result["reports"]) > 20 or not result.get("as_of") or not result.get("known_at"):
                raise ValueError("Invalid history contract")
            payload = {k: result[k] for k in ("business", "as_of", "known_at", "reports", "has_more", "next_before") if k in result}
        else:
            if not result.get("checked_at") or not isinstance(result.get("claim_kinds"), dict):
                raise ValueError("Invalid summary contract")
            payload = {k: result[k] for k in ("business", "checked_at", "attention_total", "claim_kinds", "open_pipeline", "reconciled_bookings") if k in result}
        return {"status": "available", "mode": "read_only", "source": "chrono", "retrieved_at": instant,
                "evidence_kind": "saved_external_analysis" if kind == "analysis-history" else "external_summary",
                "data": payload, "note": "Source evidence and supplied assumptions may be outdated. No forecast recalculation, dealer-data export or action execution occurred."}
    except Exception:
        return {"status": "unavailable", "mode": "read_only", "reason": "Chrono did not return an authorized response matching the business contract; check host routing, token expiry, business scope and service health"}
