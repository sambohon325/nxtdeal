from datetime import date
from copy import deepcopy
import pytest
from test_website_studio import site, config
from test_lone_star import lone_star
from core import websites, garage
from core.entities import Entity
from core.website_studio import update_studio_api, start_draft_api, validate_coupons
from core.websites_api import submit_website_api, approve_website_api
from core.website_offers import published_offers, garage_offers

TODAY=date(2026,10,20)
def coupon(**kw):
    return {"id":"oil", "enabled":True, "title":"Oil service", "titleEs":"Servicio de aceite", "summary":"Save 10", "summaryEs":"Ahorra 10", "terms":"With appointment", "termsEs":"Con cita", "code":"OIL10", "start":"2026-10-01", "end":"2026-10-31", **kw}
def publish(site, custom):
    assert "error" not in update_studio_api("SALES","owner",site.id,config(lone_star=custom),site.attributes.get("studio_revision",0))
    assert submit_website_api("SALES","owner",site.id)["status"]=="pending_approval"
    assert approve_website_api("ADMIN","reviewer",site.id)["status"]=="published"

def test_shared_feed_uses_approved_snapshot_and_live_inventory(site):
    websites.ledger.add_entity(Entity(id="truck",entity_type="Vehicle",attributes={"BodyStyle":"Truck"}))
    websites.ledger.add_entity(Entity(id="suv",entity_type="Vehicle",attributes={"BodyStyle":"SUV"}))
    custom={**lone_star(),"coupons":[coupon()]}
    assert published_offers(TODAY)=={"offers":[]}
    publish(site,custom)
    offers=published_offers(TODAY)["offers"]
    assert [v["id"] for v in offers[0]["vehicles"]]==["truck"]
    assert offers[1]["code"]=="OIL10" and offers[1]["titleEs"]=="Servicio de aceite"
    start_draft_api("SALES","owner",site.id)
    changed=deepcopy(custom);changed["coupons"][0]["title"]="Unapproved change"
    update_studio_api("SALES","owner",site.id,config(lone_star=changed),site.attributes["studio_revision"])
    assert published_offers(TODAY)["offers"][1]["title"]=="Oil service"
    websites.ledger.get_entity("truck").attributes["DateSold"]="2026-10-20"
    assert published_offers(TODAY)["offers"][0]["vehicles"]==[]

def test_dates_disabled_and_boundaries(site):
    custom={**lone_star(),"coupons":[coupon(),coupon(id="disabled",enabled=False),coupon(id="future",start="2026-12-01",end="2026-12-31")]}
    publish(site,custom)
    assert len(published_offers(date(2026,10,31))["offers"])==2
    assert len(published_offers(date(2026,11,1))["offers"])==1
    assert published_offers(date(2027,1,1))["offers"]==[]

def test_garage_requires_verified_customer(site,monkeypatch):
    monkeypatch.setattr(garage,"_resolve_customer",lambda token:(None,{"error":"Verify first"}))
    assert garage_offers("wrong")=={"error":"Verify first"}
    monkeypatch.setattr(garage,"_resolve_customer",lambda token:("customer",None))
    assert garage_offers("verified")=={"offers":[]}

@pytest.mark.parametrize("rows", [[coupon(enabled="yes")],[coupon(),coupon()],[coupon(title="")],[coupon(end="2025-01-01")],[coupon(start="invalid")],[coupon(extra="bad")]])
def test_invalid_coupon_rejected(rows):
    with pytest.raises(ValueError):validate_coupons(rows)


def test_real_garage_verification_gate_matches_shared_published_feed(site, monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    from test_garage import _customer, _session
    _customer()
    anonymous=_session(token="anon",tier="anonymous")
    assert garage_offers(anonymous)["reason"]=="unverified"
    assert garage_offers("unknown")["reason"]=="token"
    customer=_session(token="verified")
    custom={**lone_star(),"coupons":[coupon(start="",end="")]}
    publish(site,custom)
    assert garage_offers(customer)==published_offers()


def test_public_offers_endpoint_excludes_drafts_and_customer_records(site):
    from api.app import public_website_offers
    websites.ledger.add_entity(Entity(id="private-customer",entity_type="Customer",attributes={"Email":"private@example.test"}))
    assert public_website_offers()=={"offers":[]}
    custom={**lone_star(),"coupons":[coupon(start="",end="")]}
    publish(site,custom)
    result=public_website_offers()
    assert result==published_offers()
    assert "private@example.test" not in str(result)
    assert result["offers"][-1]["code"]=="OIL10"
