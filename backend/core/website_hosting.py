"""Explicitly scoped Coolify adapter for the Lone Star pilot.

Provisioning must assign one isolated gateway resource to one website. Never use a
shared staff application here. No API credential is accepted from website content.
"""
import json
import os
import re
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import ipaddress


def config(site_id):
    names = ('NXT_WEBSITE_COOLIFY_URL', 'NXT_WEBSITE_COOLIFY_TOKEN', 'NXT_WEBSITE_RESOURCE_UUID', 'NXT_WEBSITE_SITE_ID', 'NXT_WEBSITE_ALLOWED_DOMAIN')
    values = {name: os.environ.get(name, '') for name in names}
    if not values['NXT_WEBSITE_COOLIFY_URL'] or not values['NXT_WEBSITE_COOLIFY_TOKEN']:
        raise ValueError('Hosting connection has not been configured for this website')
    if values['NXT_WEBSITE_SITE_ID'] != site_id or not values['NXT_WEBSITE_RESOURCE_UUID'] or not values['NXT_WEBSITE_ALLOWED_DOMAIN']:
        from core.website_provisioning import settings, read_registry
        settings()
        entry = read_registry().get(site_id, {})
        values['automatic'] = True
        values['NXT_WEBSITE_RESOURCE_UUID'] = entry.get('resource_uuid') or 'pending'
        values['NXT_WEBSITE_ALLOWED_DOMAIN'] = entry.get('domain') or ''
    if not re.fullmatch(r'[a-zA-Z0-9-]+', values['NXT_WEBSITE_RESOURCE_UUID']):
        raise ValueError('Invalid hosting resource configuration')
    origin = urlsplit(values['NXT_WEBSITE_COOLIFY_URL'])
    try:
        internal = ipaddress.ip_address(origin.hostname or '').is_private
    except ValueError:
        internal = origin.hostname == 'localhost'
    if origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/') or not origin.hostname or not (origin.scheme == 'https' or (origin.scheme == 'http' and internal)):
        raise ValueError('Hosting control connection requires HTTPS or a private internal address')
    return values


def _request(cfg, method, path, payload=None):
    url = cfg['NXT_WEBSITE_COOLIFY_URL'].rstrip('/') + '/api/v1' + path
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization':'Bearer '+cfg['NXT_WEBSITE_COOLIFY_TOKEN'], 'Content-Type':'application/json', 'Accept':'application/json'}, method=method)
    # Do not follow a redirect carrying infrastructure credentials.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            return json.loads(response.read(1024*1024))
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise ValueError('This domain is assigned to another hosting resource. No override was made.') from None
        raise ValueError('Hosting could not complete the request. Check the platform connection.') from None
    except Exception:
        raise ValueError('Hosting is unavailable. Try again after checking the platform connection.') from None


def connect(site_id, domain):
    cfg = config(site_id)
    if cfg.get('automatic'):
        from core.website_provisioning import provision
        entry = provision(site_id, domain, cfg, _request)
        cfg['NXT_WEBSITE_RESOURCE_UUID'] = entry['resource_uuid']
        cfg['NXT_WEBSITE_ALLOWED_DOMAIN'] = entry['domain']
    if domain != cfg['NXT_WEBSITE_ALLOWED_DOMAIN']:
        raise ValueError('This pilot hosting connection is restricted to its assigned test domain')
    path = '/applications/' + cfg['NXT_WEBSITE_RESOURCE_UUID']
    app = _request(cfg, 'GET', path)
    if not isinstance(app, dict):
        raise ValueError('Invalid hosting response')
    if app.get('build_pack') != 'dockercompose':
        raise ValueError('The hosting resource must be the isolated public website gateway')
    existing = app.get('docker_compose_domains')
    if existing is None or existing == '':
        existing = {}
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except ValueError:
            raise ValueError('Invalid hosting domain configuration') from None
    if not isinstance(existing, dict):
        raise ValueError('Invalid hosting domain configuration')
    # Fail closed if any other service/domain is already exposed. Never replace
    # another website or expose the staff frontend/API by accident.
    desired = 'https://' + domain + ':8080'
    for service, entry in existing.items():
        current = entry.get('domain', '') if isinstance(entry, dict) else ''
        if not isinstance(entry, dict) or (current and (service != 'gateway' or current not in (desired, 'https://' + domain))):
            raise ValueError('Hosting has another domain mapping; platform review is required')
    _request(cfg, 'PATCH', path, {'docker_compose_domains':[{'name':'gateway','domain':desired}],
                                'is_force_https_enabled':True, 'force_domain_override':False})
    _request(cfg, 'POST', '/deploy?uuid=' + cfg['NXT_WEBSITE_RESOURCE_UUID'] + '&force=false' if cfg.get('automatic') else path+'/restart')
    return {'status':'activating', 'hosting_active':False,
            'message':'Domain sent to hosting. HTTPS must be checked before this website is marked live.'}


def readiness(site_id):
    try:
        config(site_id)
        return True
    except ValueError:
        return False


def probe(site_id, domain):
    # Only a persisted platform assignment can be probed; check routing again before HTTPS.
    cfg = config(site_id)
    if domain != cfg['NXT_WEBSITE_ALLOWED_DOMAIN']:
        raise ValueError('This domain has not been assigned to this hosting connection')
    if cfg.get('automatic'):
        from core.website_provisioning import routing, read_registry
        if not read_registry().get(site_id, {}).get('configured'):
            raise ValueError('Connect hosting before checking HTTPS')
        routing(domain)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        url = 'https://' + domain + '/api/public/websites/' + site_id
        with urllib.request.build_opener(NoRedirect).open(url, timeout=15) as response:
            data = json.loads(response.read(1024*1024))
        from core.websites import get_website
        from core.website_revisions import public_version
        published = public_version(get_website(site_id))
        if not published or data.get('id') != site_id or data.get('studio_config') != published.attributes.get('studio_config'):
            raise ValueError('Wrong website')
    except Exception:
        raise ValueError('HTTPS is not ready or the domain is serving a different website. Wait and check again.') from None
    return {'status':'live', 'hosting_active':True,
            'message':'The domain serves this approved website over verified HTTPS.'}
