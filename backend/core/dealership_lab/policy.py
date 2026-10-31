"""Hub-controlled Lab switch; strict existing network-key boundary, no fallback."""
import hmac
import os
from fastapi import HTTPException
from core.secrets import get_secret
from . import service as lab

KIND='DealershipLabPolicy'


def read():
    with lab.LOCK:
        e=next(iter(lab.items(KIND)),None)
        return lab.serial(e) if e else dict(enabled=True,revision=0,source='Default staff Lab access',updated_at=None)


def require_enabled():
    if not read()['enabled']:raise HTTPException(403,'Dealership Lab is disabled by the Hub administrator')


def authorize(key,dealer_id):
    expected=get_secret('DEALEROS_NETWORK_KEY','')
    configured=os.environ.get('NXTDEAL_DEALER_ID','')
    if not expected or len(expected)<32 or expected.startswith('dev-only-') or not configured:
        raise HTTPException(503,'Secure Hub network key and tenant identity must be configured before Lab policy synchronization')
    if not key or not hmac.compare_digest(key,expected):raise HTTPException(401,'Invalid Hub network key')
    if configured!=dealer_id:raise HTTPException(409,'Hub dealer identity does not match this tenant')


def update(key,dealer_id,enabled,revision):
    authorize(key,dealer_id)
    with lab.transaction():
        current=read()
        if current['revision']!=revision:raise HTTPException(409,'Lab policy changed; refresh the live state')
        value=dict(enabled=enabled,revision=revision+1,source='Authenticated Hub policy synchronization',dealer_id=dealer_id,updated_at=lab.now().isoformat())
        e=next(iter(lab.items(KIND)),None)
        if e:e.attributes.update(value)
        else:e=lab.create('LABC',KIND,value)
        lab.create('LABA','DealershipLabPolicyAudit',dict(**value,previous_enabled=current['enabled']))
        return lab.serial(e)
