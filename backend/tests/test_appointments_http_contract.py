"""Real router contract checks using an isolated ledger and stubbed persistence."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import appointments
from core.dealeros import ledger
from api.routers import appointments as routes

@pytest.fixture
def client(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(appointments,'save_graph',lambda *_:None)
    monkeypatch.setattr(routes,'_authenticate',lambda value: ({'role':'SALES','employee_id':'EMP-1'},None) if value else (None,{'error':'Sign in required'}))
    app=FastAPI();app.include_router(routes.router)
    yield TestClient(app)
    ledger.reset()


def test_create_accepts_nullable_optional_fields_from_frontend(client):
    payload={'department':'Sales','appointment_type':'showroom_visit','scheduled_start':'2026-10-04T10:00:00Z',
             **{key:None for key in ('assigned_to','customer_id','lead_id','vehicle_id','scheduled_end')}}
    response=client.post('/appointments',headers={'Authorization':'fixture'},json=payload)
    assert response.status_code==200
    data=response.json()
    assert data['status']=='scheduled'
    assert all(data[key] is None for key in ('assigned_to','customer_id','lead_id','vehicle_id','scheduled_end'))


def test_reschedule_accepts_null_end_and_keeps_existing_end(client):
    appt=appointments.create_appointment('Sales','showroom_visit','2026-10-04T10:00:00Z','EMP-1',scheduled_end='2026-10-04T11:00:00Z')
    response=client.post('/appointments/'+appt.id+'/reschedule',headers={'Authorization':'fixture'},json={'new_start':'2026-10-04T10:30:00Z','new_end':None})
    assert response.status_code==200
    assert response.json()['scheduled_start']=='2026-10-04T10:30:00Z'
    assert response.json()['scheduled_end']=='2026-10-04T11:00:00Z'


def test_null_required_start_rejected_without_mutation(client):
    response=client.post('/appointments',headers={'Authorization':'fixture'},json={'department':'Sales','appointment_type':'showroom_visit','scheduled_start':None})
    assert response.status_code==422
    assert appointments.list_appointments()==[]
