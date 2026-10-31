"""Explicit synthetic, loopback-only dealership for opt-in desktop integration tests.

Start from backend/: python tests/agent_desktop_fixture.py
Uses the real agent gateway and projections, an isolated ledger, and no production data.
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DEALEROS_STORAGE_DIR'] = tempfile.mkdtemp(prefix='nxtdeal-synthetic-')
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core import agent_fabric as fabric
from core import ai_spend, ai_kill_switch
from api.routers.agent_fabric import router, employee

ledger.entities, ledger.relationships = {}, []
fabric.persist = lambda: None
ai_spend.dealer_ai_enabled = lambda: True
ai_kill_switch.is_bot_enabled = lambda: True
ai_kill_switch.is_workflow_automation_enabled = lambda: True
ai_kill_switch.get_ai_kill_switches = lambda: {}
now = datetime.now(timezone.utc)
def add(identifier, kind, **attrs):
    ledger.add_entity(Entity(identifier, kind, {'synthetic': True, **attrs}))
add('SYN-EMP-1','Employee',department='Sales')
add('SYN-CUSTOMER-1','Customer',FirstName='Synthetic',LastName='Customer',consent={'email':True,'sms':False})
add('SYN-CUSTOMER-2','Customer',FirstName='Synthetic',LastName='UnknownConsent')
add('SYN-LEAD-1','Lead',PipelineState='CONTACTED',PipelineCreatedAt=(now-timedelta(days=30)).isoformat())
add('SYN-NOTE-1','FieldNote',linked_entity_id='SYN-LEAD-1',category='call',created_at=(now-timedelta(days=5)).isoformat(),body='Synthetic test call. Do not export this body.')
add('SYN-VIN-1','Vehicle',Year='2024',Make='Synthetic Motors',Model='Test Sedan',DaysInStock=95,status='available')
add('SYN-DEAL-1','Deal',status='open',created_at=(now-timedelta(days=7)).isoformat())
add('SYN-CAMP-1','Campaign',name='Synthetic aged inventory draft',status='draft',created_at=now.isoformat())
ledger.add_relationship(Relationship('SYN-EMP-1','SYN-LEAD-1','ASSIGNED_TO'))
ledger.add_relationship(Relationship('SYN-CUSTOMER-1','SYN-LEAD-1','HAS_LEAD'))
ledger.add_relationship(Relationship('SYN-LEAD-1','SYN-VIN-1','INTERESTED_IN'))
app = FastAPI()
actor={'employee_id':'fixture','role':'ADMIN'}
app.dependency_overrides[employee]=lambda:actor
@app.middleware('http')
async def read_only(request,call_next):
    if request.method!='GET':
        if request.url.path!='/agent-fabric/invoke':
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'Synthetic fixture is read-only'},status_code=403)
        body=await request.json()
        capability=fabric.CAPABILITIES.get(body.get('capability'))
        if not capability or capability.kind!='READ':
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'Synthetic fixture is read-only'},status_code=403)
    return await call_next(request)
@app.get('/auth/whoami')
def whoami(): return {**actor,'must_change_password':False}
@app.get('/fixture-info')
def info(): return {'synthetic':True,'source':'isolated real NXTDeal backend','records':len(ledger.entities)}
app.include_router(router)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8769,log_level='warning')
