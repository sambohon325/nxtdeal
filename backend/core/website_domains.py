"""Lone Star ownership verification and explicitly scoped hosting connection."""
from datetime import datetime, timezone
import re
import secrets
from core.website_revisions import WEBSITE_WRITE_LOCK
from core.websites import get_website
from core.storage_paths import GRAPH_PATH
from core.storage import save_graph


def _site(site_id):
    site = get_website(site_id)
    if not site or not site.attributes.get('studio_config'):
        raise ValueError('Choose an approved website design before connecting a domain')
    domain = (site.attributes.get('admin_settings') or {}).get('custom_domain') or ''
    labels = domain.split('.')
    if len(domain) > 253 or len(labels) < 2 or labels[-1].isdigit() or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in labels):
        raise ValueError('Save a valid website domain first')
    return site, domain


def _view(domain, record, site_id=None):
    from core import website_hosting
    return {'domain': domain, 'txt_host': '_nxtdeal.' + domain,
            'txt_value': record.get('token'), 'ownership_verified': record.get('ownership_verified', False),
            'checked_at': record.get('checked_at'), 'hosting_active': record.get('hosting_active', False),
            'hosting_configured': website_hosting.readiness(site_id),
            'hosting_checked_at': record.get('hosting_checked_at'), 'status': record.get('status', 'pending'),
            'message': record.get('message', 'Prepare your ownership record to begin.')}


def status(site_id):
    with WEBSITE_WRITE_LOCK:
        site, domain = _site(site_id)
        record = site.attributes.get('domain_verification') or {}
        if record.get('domain') != domain:
            record = {}
        return _view(domain, record, site_id)


def prepare(site_id):
    with WEBSITE_WRITE_LOCK:
        site, domain = _site(site_id)
        record = site.attributes.get('domain_verification') or {}
        if record.get('domain') != domain or not record.get('token'):
            record = {'domain': domain, 'token': 'nxtdeal-verification=' + secrets.token_urlsafe(32)}
            site.attributes['domain_verification'] = record
            save_graph(GRAPH_PATH)
        return _view(domain, record, site_id)


def _txt_values(host):
    import dns.resolver
    resolver = dns.resolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 5
    return [b''.join(answer.strings).decode('ascii', errors='replace') for answer in resolver.resolve(host, 'TXT')]


def verify(site_id):
    with WEBSITE_WRITE_LOCK:
        site, domain = _site(site_id)
        record = dict(site.attributes.get('domain_verification') or {})
        if record.get('domain') != domain or not record.get('token'):
            raise ValueError('Prepare the ownership record first')
    try:
        verified = record['token'] in _txt_values('_nxtdeal.' + domain)
        message = 'Domain ownership verified. Hosting activation is still required.' if verified else 'TXT record not found yet. Check the name and value with your DNS provider, then try again.'
    except Exception:
        verified = False
        message = 'DNS could not be verified. Check the TXT record and allow time for DNS changes, then try again.'
    with WEBSITE_WRITE_LOCK:
        site, current_domain = _site(site_id)
        current = site.attributes.get('domain_verification') or {}
        if current_domain != domain or current.get('token') != record['token']:
            raise ValueError('The domain changed during verification. Prepare its new ownership record.')
        current.update(hosting_active=False, ownership_verified=verified, checked_at=datetime.now(timezone.utc).isoformat(), message=message)
        save_graph(GRAPH_PATH)
        return _view(domain, current, site_id)


def _hosting_action(site_id, action):
    from core import website_hosting
    from core.website_revisions import public_version
    # Refresh ownership before every infrastructure operation. A saved green badge
    # is not authorization after DNS ownership has changed.
    if not verify(site_id)['ownership_verified']:
        raise ValueError('Verify the domain ownership TXT record first')
    with WEBSITE_WRITE_LOCK:
        site, domain = _site(site_id)
        record = site.attributes.get('domain_verification') or {}
        if record.get('domain') != domain or not record.get('ownership_verified'):
            raise ValueError('Domain changed. Verify its ownership again.')
        published = public_version(site)
        if not published or (published.attributes.get('admin_settings') or {}).get('custom_domain') != domain:
            raise ValueError('Approve the website version with this domain before connecting hosting')
        # Serializes domain edits and duplicate activations on the existing single-process tenant store.
        result = getattr(website_hosting, action)(site_id, domain)
        record = site.attributes['domain_verification']
        record.update(result, hosting_checked_at=datetime.now(timezone.utc).isoformat())
        save_graph(GRAPH_PATH)
        return _view(domain, record, site_id)


def activate(site_id):
    return _hosting_action(site_id, 'connect')


def check_https(site_id):
    return _hosting_action(site_id, 'probe')
