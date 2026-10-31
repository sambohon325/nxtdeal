"""
hub/app_signup_routes.py -- drop-in FastAPI routes for self-serve signup + the inactivity lifecycle
(NXTDeal Freemium, 2026-08-03).

These are written as a separate router so they slot into the real hub/app.py with one line, without
me having to guess the rest of that file's structure:

    # in hub/app.py, after `app = FastAPI(...)`:
    from hub.app_signup_routes import router as signup_router, bind_signup
    bind_signup()                      # binds the dealer store + provisioner (see below)
    app.include_router(signup_router)

`bind_signup()` is where you connect the logic to the Hub's real dealer store + Coolify provisioner.
Edit it to match hub/core/dealer.py + hub_core/infra_provisioning.py (the two TODOs). Until you do,
it falls back to the in-memory reference store so the endpoints work end-to-end in dev.

Endpoints:
  POST /public/signup                 -- PUBLIC (no auth): the marketing "Start Free" funnel target.
  GET  /public/signup/business-types  -- PUBLIC: the "what kind of business are you?" options.
  POST /hub/dealers/{id}/activity     -- record activity / reactivate (call on dealer login).
  GET  /hub/dealers/{id}/lifecycle    -- lifecycle status for the dealer record UI.
  POST /hub/lifecycle/sweep           -- run the inactivity sweep (Hub cron / admin). Protect this.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from hub.core import dealer_signup, dealer_lifecycle

router = APIRouter()


# ---------------------------------------------------------------------------
# Binding -- connect the logic to the real Hub store + provisioner. EDIT THE TODOs.
# ---------------------------------------------------------------------------

def bind_signup():
    """Bind the signup + lifecycle logic to the Hub's real dealer store and Coolify provisioner.

    Replace the two TODOs with your real hub/core/dealer.py + hub_core/infra_provisioning.py. Until
    then, both default to the in-memory reference store so /public/signup works in dev."""

    # --- TODO(1): dealer store adapter over hub/core/dealer.py ---
    # from hub.core import dealer
    # class HubDealerStore:
    #     def all(self): return dealer.list_dealers()
    #     def get(self, i): return dealer.get_dealer(i)
    #     def create(self, r): return dealer.create_dealer(r)
    #     def save(self, r): return dealer.update_dealer(r["dealer_id"], r)
    #     def delete(self, i): return dealer.delete_dealer(i)
    # store = HubDealerStore()
    # dealer_signup.set_store(store)
    # dealer_lifecycle.set_store(store)

    # --- TODO(2): provisioner over hub_core/infra_provisioning.py ---
    # from hub_core import infra_provisioning
    # def provision(record):
    #     res = infra_provisioning.provision_dealer(record["dealer_id"])  # your real signature
    #     return {"api_url": res.get("api", {}).get("url"), "frontend_url": res.get("frontend", {}).get("url")}
    # dealer_signup.set_provisioner(provision)
    return


# ---------------------------------------------------------------------------
# Public self-serve signup (the "Start Free" target)
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str = ""
    work_email: str
    dealership_name: str
    business_type: str
    contact_phone: str | None = None
    network_opt_in: bool = True


@router.post("/public/signup")
def public_signup(request: SignupRequest):
    """PUBLIC. Creates a free Foundation dealer account and starts provisioning. No auth -- this is
    the marketing-site conversion path. Rate-limit / captcha this at the edge in production."""
    return dealer_signup.self_serve_signup(
        request.name, request.work_email, request.dealership_name, request.business_type,
        contact_phone=request.contact_phone, network_opt_in=request.network_opt_in,
    )


@router.get("/public/signup/business-types")
def public_business_types():
    """PUBLIC. The 'What kind of business are you?' options for the Start Free selector."""
    return {"business_types": dealer_signup.list_business_types()}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@router.post("/hub/dealers/{dealer_id}/activity")
def dealer_activity(dealer_id: str):
    """Record dealer activity (call on any dealer login / product heartbeat). Reactivates an
    inactivity-deactivated instance -- this is the 'unless re-logged into' path."""
    return dealer_lifecycle.record_dealer_activity(dealer_id)


@router.get("/hub/dealers/{dealer_id}/lifecycle")
def dealer_lifecycle_status(dealer_id: str):
    return dealer_lifecycle.lifecycle_status(dealer_id)


@router.post("/hub/lifecycle/sweep")
def lifecycle_sweep(authorization: str = Header(None)):
    """Run the inactivity sweep: deactivate dealers inactive >6mo, delete those deactivated >6mo
    (12mo total). Idempotent -- wire to the Hub's daily cron. PROTECT THIS (admin/cron secret) in
    production; add your Hub's auth check here."""
    return dealer_lifecycle.sweep()
