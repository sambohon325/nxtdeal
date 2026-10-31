"""Public, bounded telemetry. No IPs, contact fields or full referrer URLs retained."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID
from core import websites as w
from core.website_revisions import has_public_version

PAGES = {'home','main','inventory','payment-shop','financing','team','trade','service','promotions','contact','vehicle'}

@w.serialized_website_write
def collect(website_id, data, user_agent=''):
    if not has_public_version(w.get_website(website_id)):
        return {'error':'Site not found'}
    try:
        event_id=str(UUID(str(data.get('id')))); session=str(UUID(str(data.get('session'))))
    except (ValueError, TypeError, AttributeError):
        return {'error':'Invalid event identifier'}
    kind=data.get('event'); page=data.get('page','home')
    if kind not in ('page_view','section_view','vehicle_view') or page not in PAGES:
        return {'error':'Invalid event'}
    device=data.get('device','unknown')
    if device not in ('desktop','mobile','tablet','unknown'): return {'error':'Invalid device'}
    entity_id='WEBSTAT-'+website_id+'-'+event_id
    if entity_id in w.ledger.get_all(): return {'ok':True}
    now=datetime.now(timezone.utc)
    # Bounded per-session writes; endpoint also has a per-client ingress limit.
    recent=[e for e in w.ledger.get_all().values() if e.entity_type=='WebsiteVisit' and e.attributes.get('WebsiteID')==website_id and e.attributes.get('Session')==session and e.attributes.get('Timestamp','')>=(now-timedelta(minutes=1)).isoformat()]
    if len(recent)>=30: return {'error':'Too many events'}
    raw=str(data.get('source',''))[:200]
    source=raw if __import__('re').fullmatch(r'[a-zA-Z0-9_.-]{1,60}',raw) else 'Direct / unknown'
    ua=(user_agent or '').lower()
    browser=next((name for token,name in [('edg/','Edge'),('firefox/','Firefox'),('chrome/','Chrome'),('safari/','Safari')] if token in ua),'Other')
    bot,_=w._classify_user_agent(user_agent)
    attrs={'WebsiteID':website_id,'Session':session,'Event':kind,'Page':page,'Device':device,'Browser':browser,'Source':source,'IsBot':bot,'Timestamp':now.isoformat()}
    entity=w.Entity(id=entity_id,entity_type='WebsiteVisit',attributes=attrs)
    w.ledger.add_entity(entity)
    try: w.save_graph(w.GRAPH_PATH)
    except Exception:
        w.ledger.entities.pop(entity_id,None)
        raise
    return {'ok':True}

def report(website_id, days=30):
    days=max(1,min(int(days),90)); now=datetime.now(timezone.utc); cutoff=(now-timedelta(days=days-1)).date().isoformat()
    rows=[e.attributes for e in w.ledger.get_all().values() if e.entity_type=='WebsiteVisit' and e.attributes.get('WebsiteID')==website_id and e.attributes.get('Timestamp','')[:10]>=cutoff]
    humans=[r for r in rows if not r.get('IsBot')]; views=[r for r in humans if r['Event']=='page_view']; sessions={r['Session'] for r in humans}
    leads=[e for e in w.ledger.get_all().values() if e.entity_type=='Lead' and e.attributes.get('WebsiteID')==website_id and str(e.attributes.get('CreatedAt') or e.attributes.get('created_at') or '')[:10]>=cutoff]
    conversion_counts=Counter(e.attributes.get('WebsiteInquiryIntent') or 'information' for e in leads)
    month_cutoff=(now-timedelta(days=29)).date().isoformat()
    monthly=[e for e in w.ledger.get_all().values() if e.entity_type=='Lead' and e.attributes.get('WebsiteID')==website_id and str(e.attributes.get('CreatedAt') or '')[:10]>=month_cutoff]
    monthly_counts=Counter(e.attributes.get('WebsiteInquiryIntent') or 'information' for e in monthly)
    site=w.get_website(website_id)
    goals=((site.attributes.get('admin_settings') or {}).get('conversion_goals',[]) if site else [])
    goal_progress=[{**g,'actual':len(monthly) if g['metric']=='all' else monthly_counts[g['metric']]} for g in goals if g['enabled']]
    counts=Counter(r['Timestamp'][:10] for r in views)
    return {'conversions':dict(conversion_counts),'goals':goal_progress,'days':days,'sessions':len(sessions),'pageviews':len(views),'leads':len(leads),'active_sessions':len({r['Session'] for r in humans if r['Timestamp']>=(now-timedelta(minutes=5)).isoformat()}),'by_day':{(now-timedelta(days=i)).date().isoformat():counts[(now-timedelta(days=i)).date().isoformat()] for i in reversed(range(days))},'sources':dict(Counter(r['Source'] for r in views).most_common(10)),'devices':dict(Counter(r['Device'] for r in views)),'browsers':dict(Counter(r['Browser'] for r in views)),'pages':dict(Counter(r['Page'] for r in humans).most_common(15)),'events':dict(Counter(r['Event'] for r in humans)),'bot_events':len(rows)-len(humans),'note':'Public website activity only. Sessions are per browser tab and expire after 30 minutes of inactivity. Preview and historical render requests are excluded. Sources and devices are browser-reported. Leads count persisted website inquiries; no visitor fingerprinting.'}
