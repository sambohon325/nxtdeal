"""Explicit Lab policy synchronization, using the existing recorded tenant API."""
import json
import urllib.request
import urllib.parse
import urllib.error
from hub_core.secrets import get_secret
from hub_core.dealer_registry import registry
from hub_core.dealer_modules import get_dealer_module_config
from hub_core.hub_audit_api import record_and_save


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def exchange(dealer_id,body=None):
    dealer=registry.get(dealer_id)
    if not dealer:raise ValueError('Dealer not found')
    key=get_secret('DEALEROS_NETWORK_KEY','')
    if not key or len(key)<32 or key.startswith('dev-only-'):raise ValueError('Configure a secure Hub network key before synchronization')
    base=dealer.api_base_url or '';parsed=urllib.parse.urlsplit(base)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('A verified HTTPS tenant API address is required')
    url=base.rstrip('/')+'/network/dealership-lab-policy'
    if body is None:url+='?'+urllib.parse.urlencode(dict(dealer_id=dealer_id))
    request=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,
        headers={'Accept':'application/json','Content-Type':'application/json','X-NXTDeal-Network-Key':key})
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=10) as response:
            raw=response.read(32769)
            if len(raw)>32768:raise ValueError('Tenant policy response exceeded its limit')
            data=json.loads(raw)
    except (urllib.error.URLError,json.JSONDecodeError) as exc:
        raise ValueError('Tenant policy check failed. Verify deployment, HTTPS, network key and matching NXTDEAL_DEALER_ID.') from exc
    if not isinstance(data,dict) or type(data.get('enabled')) is not bool or type(data.get('revision')) is not int:
        raise ValueError('Tenant returned an invalid policy receipt')
    return data


def status(dealer_id):
    desired=next(m['enabled'] for m in get_dealer_module_config(dealer_id)['modules'] if m['key']=='network')
    live=exchange(dealer_id)
    return dict(dealer_id=dealer_id,desired=desired,live=live,synchronized=desired==live['enabled'])


def synchronize(dealer_id,revision,actor):
    desired=next(m['enabled'] for m in get_dealer_module_config(dealer_id)['modules'] if m['key']=='network')
    try:
        receipt=exchange(dealer_id,dict(dealer_id=dealer_id,enabled=desired,revision=revision))
        if receipt['enabled']!=desired or receipt['revision']!=revision+1:raise ValueError('Tenant receipt did not confirm the requested policy')
    except ValueError:
        record_and_save(event_type='lab_policy_sync_failed',summary='Lab policy synchronization failed; inspect live state before retrying',dealer_id=dealer_id,actor=actor,details={'desired':desired})
        raise
    record_and_save(event_type='lab_policy_synchronized',summary='Tenant confirmed dealership Lab policy',dealer_id=dealer_id,actor=actor,details={'enabled':desired,'revision':receipt['revision']})
    return dict(dealer_id=dealer_id,desired=desired,live=receipt,synchronized=True)
