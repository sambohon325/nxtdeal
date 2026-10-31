import pytest
from test_website_studio import site, config
from core import websites
from core.website_studio import update_studio_api, validate_config, studio_inventory_api
from core.dealeros import ledger
from core.entities import Entity

def lone_star():
    return {"name":"Synthetic Lone Star","headline":"Ready for your road","intro":"Intro","story":"History","hero":"/website-studio/assets/lone-star-truck-hero.png","teamPhoto":"/website-studio/assets/lone-star-about-team.png","locations":[{"id":"north","name":"North","address":"Synthetic","phone":"5550100000","hours":"Weekdays"}],"socials":{},"backgrounds":{},"event":{"template":"fall","enabled":True,"bannerEnabled":True,"title":"Fall","titleEs":"Otono","summary":"Stock","summaryEs":"Stock","terms":"Terms","termsEs":"Terms","start":"2026-10-01","end":"2026-11-30","target":"type","bodyType":"Truck","banner":"","event":""}}

def test_saved_owner_revision_and_review_gates(site):
    settings=config(lone_star=lone_star())
    assert "error" in update_studio_api("SALES","other",site.id,settings,0)
    assert update_studio_api("SALES","owner",site.id,settings,0)["studio_config"]["lone_star"]==lone_star()
    assert websites.get_website(site.id).attributes["studio_config"]["lone_star"]["headline"]=="Ready for your road"
    assert "error" in update_studio_api("SALES","owner",site.id,settings,0)
    site.attributes["status"]="pending_approval"
    assert "error" in update_studio_api("ADMIN","owner",site.id,settings,1)

@pytest.mark.parametrize("change",[{"hero":"data:image/png;base64,a"},{"hero":"javascript:alert(1)"},{"socials":{"Instagram":"http://example.test"}},{"locations":[{"id":"x","name":""}]},{"event":{"template":"missing"}}])
def test_invalid_settings(change):
    with pytest.raises(ValueError):validate_config(config(lone_star={**lone_star(),**change}))

def test_failed_save_rolls_back(site,monkeypatch):
    def fail(*args):raise OSError("synthetic disk failure")
    monkeypatch.setattr(websites,"save_graph",fail)
    with pytest.raises(OSError):update_studio_api("SALES","owner",site.id,config(lone_star=lone_star()),0)
    assert "studio_config" not in site.attributes
    assert site.attributes.get("studio_revision",0)==0

def test_canonical_inventory_excludes_sold(site):
    ledger.add_entity(Entity(id="stock-truck",entity_type="Vehicle",attributes={"Make":"Test","BodyStyle":"Truck","StockNumber":"T1"}))
    ledger.add_entity(Entity(id="sold",entity_type="Vehicle",attributes={"DateSold":"2026-01-01"}))
    rows=studio_inventory_api("SALES","owner",site.id)
    assert [row["id"] for row in rows]==["stock-truck"]
    assert rows[0]["body_type"]=="Truck" and rows[0]["photos"]==[]
    assert "error" in studio_inventory_api("SALES","other",site.id)

def test_lone_star_public_flow_and_draft_isolation(site):
    from core.websites_api import submit_website_api, approve_website_api, submit_contact_form_api
    from core.website_studio import start_draft_api, public_inventory_api
    from uuid import uuid4
    site.attributes['pages']['contact']['sections']=[{'section_key':'contact_form','fields':{},'locked':False}]
    update_studio_api('SALES','owner',site.id,config(lone_star=lone_star()),0)
    assert 'error' in submit_contact_form_api(site.id,'contact',0,'Test',email='test@example.test')
    assert submit_website_api('SALES','owner',site.id)['status']=='pending_approval'
    assert approve_website_api('ADMIN','reviewer',site.id)['status']=='published'
    ledger.add_entity(Entity(id='canonical-truck',entity_type='Vehicle',attributes={'Make':'Test','VIN':'SYN-TRUCK'}))
    assert public_inventory_api(site.id)['vehicles'][0]['id']=='canonical-truck'
    key=str(uuid4())
    args=(site.id,'contact',0,'Synthetic Buyer')
    kw={'email':'test@example.test','vehicle_id':'canonical-truck','intent':'purchase','request_id':key}
    first=submit_contact_form_api(*args,**kw)
    assert 'lead_id' in first,first
    assert submit_contact_form_api(*args,**kw)==first
    lead=ledger.get_entity(first['lead_id'])
    assert lead.attributes['WebsiteVehicleID']=='canonical-truck'
    assert lead.attributes['AssignedSalesperson']=='owner'
    ledger.get_entity('canonical-truck').attributes['DateSold']='2026-10-20'
    assert public_inventory_api(site.id)['total']==0
    assert 'error' in submit_contact_form_api(*args,**{**kw,'request_id':str(uuid4())})
    draft=start_draft_api('SALES','owner',site.id)
    changed=lone_star();changed['headline']='Not approved'
    update_studio_api('SALES','owner',site.id,config(lone_star=changed),draft['studio_revision'])
    public=websites.get_website_rendered(site.id,published=True)
    assert public['studio_config']['lone_star']['headline']=='Ready for your road'
