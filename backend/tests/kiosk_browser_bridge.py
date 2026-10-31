"""Private stdio fixture for the browser harness; never a production HTTP service."""
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys

root = Path(os.environ['DEALEROS_STORAGE_DIR']).resolve()
assert root.name == 'tenant' and root.parent.name.startswith('nxtdeal-kiosk-browser-')
assert not root.exists(), 'Fixture refuses existing storage'
root.mkdir()
(root / 'graph.json').write_text('{"entities":[],"relationships":[]}')
original_connect = socket.socket.connect
def local_connect(self, address):
    if isinstance(address, tuple):
        assert ipaddress.ip_address(address[0]).is_loopback, 'External network forbidden'
    return original_connect(self, address)
socket.socket.connect = local_connect

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from core import auth, auth_api, mfa
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD
from core.kiosk_sessions import KioskSessions
from core.kiosk_checkin import KioskCheckin
from core.kiosk_journal import KioskJournal
from api.routers.kiosk import create_kiosk_router

auth.credential_store.set_credential('SYN-ADMIN', 'fictional-password', 'ADMIN', must_change_password=False)
secret = auth.credential_store.begin_mfa_enrollment('SYN-ADMIN')['secret']
assert auth.credential_store.confirm_mfa_enrollment('SYN-ADMIN', mfa.totp_now(secret))['success']
ledger.add_entity(Entity(id='SYN-REP', entity_type=EMPLOYEE, attributes={'Department': 'Sales', 'FirstName': 'Fictional'}))
sessions = KioskSessions('synthetic-browser')
journal = KioskJournal(root / 'kiosk.sqlite', b'fictional-browser-journal-key-only', initialize=True)
app = FastAPI()  # No production lifespan or background workers.
app.include_router(create_kiosk_router(sessions, enabled=True, checkin=KioskCheckin(sessions, journal=journal)))
class Login(BaseModel):
    employee_id: str
    password: str
class MFA(BaseModel):
    mfa_challenge_token: str
    code: str
@app.post('/auth/login')
def login(body: Login):
    return auth_api.login(body.employee_id, body.password, client_ip='127.0.0.1')
@app.post('/auth/mfa/verify')
def verify(body: MFA):
    return auth_api.verify_mfa_login(body.mfa_challenge_token, body.code)

with TestClient(app) as client:
    for line in sys.stdin:
        item = json.loads(line)
        try:
            if item['path'] == '__fixture_totp':
                data = {'code': mfa.totp_now(secret)}
                status = 200
            elif item['path'] == '__fixture_evidence':
                leads = [e for e in ledger.get_all().values() if e.entity_type == LEAD]
                data = {'leads': len(leads), 'assigned': [e.attributes.get('AssignedSalesperson') for e in leads],
                        'active_grants': len(sessions._grants)}
                status = 200
            else:
                response = client.post(item['path'], json=item['body'], headers=item.get('headers', {}))
                data, status = response.json(), response.status_code
            print('KIOSK_RESULT ' + json.dumps({'id': item['id'], 'status': status, 'data': data}), flush=True)
        except Exception:
            print('KIOSK_RESULT ' + json.dumps({'id': item['id'], 'status': 500, 'data': {'error': 'Fixture failed'}}), flush=True)
