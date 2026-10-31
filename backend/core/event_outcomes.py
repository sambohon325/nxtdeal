"""Event results from explicit campaign-response links; never inferred from attendance."""
from decimal import Decimal
from core.dealeros import ledger

def summarize_event_outcomes(campaign_ids):
    from api.routers.campaign_workflow import CASE, projection
    rows=[projection(e) for e in ledger.get_all().values() if e.entity_type==CASE and e.attributes.get('campaign_id') in campaign_ids]
    complete=[r for r in rows if r['stage'] in {'sale_completed','service_completed'} and not r.get('link_issues')]
    seen=set();values={};unknown=0
    for row in complete:
        record_id=row.get('outcome_id')
        if not record_id or record_id in seen:continue
        seen.add(record_id)
        if row.get('recorded_value') is None:unknown+=1;continue
        currency=row.get('currency') or 'Unspecified'
        values[currency]=values.get(currency,Decimal('0'))+Decimal(str(row['recorded_value']))
    return {'responses':len(rows),'completed_outcomes':len(seen),'values_by_currency':{k:float(v) for k,v in values.items()},'missing_values':unknown,'follow_up_due':sum(not r.get('closed') and r['stage'] not in {'sale_completed','service_completed'} for r in rows),'basis':'Only explicitly linked funded sales and completed service records are counted once. Values show association, not incremental revenue or profit. Unlinked attendee purchases are not counted.'}
