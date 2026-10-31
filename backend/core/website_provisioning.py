"""Tenant-owned public gateway assignments. No infrastructure IDs come from site content."""
import ipaddress
import json
import os
import re
import secrets
from pathlib import Path
from core.storage_paths import storage_path


def settings():
    values = {key: os.environ.get('NXT_WEBSITE_' + key, '') for key in
              ('TEMPLATE_UUID', 'DESTINATION_UUID', 'TEMPLATE_COMMIT', 'ROUTING_IPS')}
    if not all(values.values()):
        raise ValueError('Automatic website hosting is not configured')
    for key in ('TEMPLATE_UUID', 'DESTINATION_UUID'):
        if not re.fullmatch(r'[A-Za-z0-9-]+', values[key]):
            raise ValueError('Invalid public hosting template configuration')
    if not re.fullmatch(r'[a-f0-9]{40}', values['TEMPLATE_COMMIT']):
        raise ValueError('Public hosting template must use an approved pinned release')
    addresses = {str(ipaddress.ip_address(x.strip())) for x in values['ROUTING_IPS'].split(',')}
    if not addresses or not all(ipaddress.ip_address(x).is_global for x in addresses):
        raise ValueError('Hosting routing addresses must be public')
    values['addresses'] = addresses
    return values


def read_registry():
    path = Path(storage_path('website-hosting.json'))
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except Exception:
        raise ValueError('Hosting assignments could not be read. Platform review is required.') from None


def save_registry(value):
    path = Path(storage_path('website-hosting.json'))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def routing(domain):
    import dns.resolver
    config = settings()
    resolver = dns.resolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 5
    addresses = set()
    for kind in ('A', 'AAAA'):
        try:
            addresses.update(str(ipaddress.ip_address(str(x))) for x in resolver.resolve(domain, kind))
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            pass
        except Exception:
            raise ValueError('DNS routing could not be checked. Allow propagation and try again.') from None
    if not addresses or not addresses.issubset(config['addresses']):
        raise ValueError('Point this domain to the supplied hosting address and remove conflicting A or AAAA records before connecting.')
    return True


def _validate_template(app, config):
    if (not isinstance(app, dict) or app.get('build_pack') != 'dockercompose'
            or app.get('docker_compose_location') != '/compose.website-public.yaml'
            or app.get('git_commit_sha') != config['TEMPLATE_COMMIT']
            or (app.get('settings') or {}).get('is_auto_deploy_enabled') is not False):
        raise ValueError('Public hosting template must be pinned and have automatic source deployments disabled')


def provision(site_id, domain, control, request):
    """Called under WEBSITE_WRITE_LOCK after fresh ownership and publication checks."""
    if not re.fullmatch(r'SITE-[A-Za-z0-9-]+', site_id):
        raise ValueError('Invalid website identifier')
    config = settings()
    routing(domain)
    registry = read_registry()
    for other_site, entry in registry.items():
        if other_site != site_id and entry.get('domain') == domain:
            raise ValueError('This domain is assigned to another website')
    entry = registry.get(site_id)
    if entry and entry['domain'] != domain:
        raise ValueError('An existing hosted domain must be disconnected by the platform before changing its assignment')
    if entry and entry.get('configured'):
        return entry
    template = request(control, 'GET', '/applications/' + config['TEMPLATE_UUID'])
    _validate_template(template, config)
    storage = request(control, 'GET', '/applications/' + config['TEMPLATE_UUID'] + '/storages')
    if (not isinstance(storage, dict) or 'persistent_storages' not in storage or 'file_storages' not in storage
            or storage['file_storages'] or any(v.get('host_path') or v.get('standalone_sqlite_id')
                                             for v in storage['persistent_storages'])):
        raise ValueError('Public hosting template cannot share host files or databases')
    if not entry:
        entry = {'domain': domain, 'name': 'NXTDeal-' + site_id + '-' + secrets.token_hex(8),
                 'template_uuid': config['TEMPLATE_UUID'], 'commit': config['TEMPLATE_COMMIT']}
        registry[site_id] = entry
        save_registry(registry)
    if entry.get('template_uuid') != config['TEMPLATE_UUID'] or entry.get('commit') != config['TEMPLATE_COMMIT']:
        raise ValueError('Hosting template changed during setup. Platform review is required.')
    if not entry.get('resource_uuid'):
        if entry.get('clone_requested'):
            # A timed-out clone may have succeeded. Recover only this persisted,
            # unpredictable operation name; never issue a second clone blindly.
            apps = request(control, 'GET', '/applications')
            matches = [a for a in apps if a.get('name') == entry['name']] if isinstance(apps, list) else []
            if len(matches) != 1:
                raise ValueError('Hosting creation is awaiting confirmation. Retry shortly; no duplicate resource was created.')
            entry['resource_uuid'] = matches[0]['uuid']
        else:
            entry['clone_requested'] = True
            save_registry(registry)
            result = request(control, 'POST', '/applications/' + config['TEMPLATE_UUID'] + '/clone',
                             {'destination_uuid': config['DESTINATION_UUID'], 'name': entry['name'], 'clone_volumes': False})
            entry['resource_uuid'] = result.get('uuid') if isinstance(result, dict) else None
        if not re.fullmatch(r'[A-Za-z0-9-]+', entry.get('resource_uuid') or ''):
            raise ValueError('Hosting did not return a valid assignment')
        save_registry(registry)
    path = '/applications/' + entry['resource_uuid']
    app = request(control, 'GET', path)
    _validate_template(app, config)
    if app.get('name') != entry['name'] or not str(app.get('status', '')).startswith('exited'):
        raise ValueError('New hosting resource is not safely stopped. Platform review is required.')
    # A clone inherits its source's domain and SITE ID. Replace both while stopped,
    # before any start/deploy request. Existing source resource is never modified.
    request(control, 'PATCH', path + '/envs', {'key': 'NXT_PUBLIC_SITE_ID', 'value': site_id, 'is_preview': False})
    request(control, 'PATCH', path, {'docker_compose_domains': [{'name': 'gateway', 'domain': 'https://' + domain + ':8080'}],
                                   'is_force_https_enabled': True, 'force_domain_override': False})
    entry['configured'] = True
    save_registry(registry)
    return entry
