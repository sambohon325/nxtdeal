from datetime import datetime, timedelta, timezone
import pytest
from tests.test_agent_fabric import isolate, SALES
from core import agent_fabric as fabric
from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship

def test_canonical_assignment_contact_and_customer_links_are_projected():
    lead = ledger.get_entity('lead-1')
    lead.attributes.pop('last_activity_at')
    ledger.add_entity(Entity('employee-1', 'Employee', {'password': 'private'}))
    ledger.add_entity(Entity('customer-1', 'Customer', {'SSN': 'private'}))
    ledger.add_relationship(Relationship('employee-1','lead-1','ASSIGNED_TO'))
    ledger.add_relationship(Relationship('lead-1','customer-1','BECAME'))
    at = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    ledger.add_entity(Entity('note-1','FieldNote',{'linked_entity_id':'lead-1','category':'call','created_at':at,'body':'private'}))
    result = fabric.invoke(SALES,'sales','lead.read',{'record_id':'lead-1'})
    attrs = result['records'][0]['attributes']
    assert attrs['assigned_to']=='employee-1'
    assert attrs['last_activity_at']==at
    assert attrs['customer_ids']==['customer-1']
    assert 'private' not in str(result)
    decision = fabric.invoke(SALES,'sales','sales.next_best_action',{'record_id':'lead-1'})
    assert decision['decision']=='review_timeline'
    timeline = fabric.invoke(SALES,'sales','customer.timeline.read',{'record_id':attrs['customer_ids'][0]})
    assert 'lead-1' in timeline['source_records']

def test_unlinked_lead_does_not_invent_customer_or_owner():
    attrs = fabric.invoke(SALES,'sales','lead.read',{'record_id':'lead-1'})['records'][0]['attributes']
    assert attrs['customer_ids']==[]
    assert 'assigned_to' not in attrs

def test_future_and_unrelated_notes_do_not_replace_observed_activity():
    before = ledger.get_entity('lead-1').attributes['last_activity_at']
    for identifier, linked, at in [('future','lead-1',(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()),('unrelated','other',datetime.now(timezone.utc).isoformat())]:
        ledger.add_entity(Entity(identifier,'FieldNote',{'linked_entity_id':linked,'category':'email','created_at':at}))
    attrs = fabric.project(ledger.get_entity('lead-1'))['attributes']
    assert attrs['last_activity_at']==before

def test_required_record_contract_is_shared_by_catalog_and_manifest():
    catalog = fabric.catalog(SALES)['agents'][0]
    for identifier in ('customer.timeline.read','sales.next_best_action','inventory.match'):
        tool=next(t for t in catalog['tools'] if t['id']==identifier)
        assert tool['input_schema']['required']==['record_id']
        with pytest.raises(ValueError): fabric.invoke(SALES,'sales',identifier,{})
    with pytest.raises(ValueError):
        fabric.invoke(SALES,'sales','customer.timeline.read',{'record_id':'lead-1'})

def test_segment_filter_rejects_invented_ids_and_returns_selected_consent():
    from tests.test_agent_fabric import ADMIN
    ledger.add_entity(Entity('consented', 'Customer', {'consent': {'email': True}}))
    ledger.add_entity(Entity('unknown', 'Customer', {}))
    result = fabric.invoke(ADMIN, 'marketing', 'customer.segment.read', {'record_id': 'consented'})
    assert result['scope'] == 'customer' and result['record_id'] == 'consented'
    assert result['segments']['all_customers'] == 1
    assert result['segments']['explicit_email_consent'] == 1
    assert result['records'] == [{'id': 'consented', 'entity_type': 'Customer', 'eligible_channels': ['email']}]
    result = fabric.invoke(ADMIN, 'marketing', 'customer.segment.read', {'record_id': 'unknown'})
    assert result['segments']['explicit_email_consent'] == 0
    assert result['records'][0]['eligible_channels'] == []
    for identifier in ('invented', 'lead-1'):
        with pytest.raises(PermissionError):
            fabric.invoke(ADMIN, 'marketing', 'customer.segment.read', {'record_id': identifier})
