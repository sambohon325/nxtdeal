"""Illustrative sales rows from an existing canonical path; never executes a simulation."""
from .earnings import cashflow


def sample_register(e, rows, side):
    """One explicitly synthetic path, kept separate from ensemble means."""
    if side not in ('baseline', 'scenario'):
        raise ValueError('Unknown model side')
    cash=cashflow(rows,e,side);deals=[]
    models=['Toyota Camry','Honda Accord','Ford Escape','Chevrolet Malibu','Nissan Rogue','Hyundai Sonata']
    bhph='BHPH' in e['dealership']['kind'];p=e['finance'][side]
    for i,row in enumerate(rows):
        for segment in ('new','used'):
            stock=[v for v in e.get('mix',{}).get('inventory',[]) if v['condition']==segment]
            units=int(row[segment+'_sales']);price=e['segments'][segment]['price'];cost=max(0,price-e['segments'][segment]['gross'])
            for j in range(min(units,max(0,2000-len(deals)))):
                # Deterministic mix approximates the entered financed share in this example register.
                financed=bhph and segment=='used' and j<round(units*p['financed_share']/100)
                down=min(price,p['down_payment']) if financed else price
                deals.append(dict(id=f'SYN-{i+1:02d}-{segment}-{j+1:04d}',month=i+1,vehicle=(str(stock[(i+j)%len(stock)]['year'])+' '+stock[(i+j)%len(stock)]['make']+' '+stock[(i+j)%len(stock)]['model']) if stock else models[(i+j)%len(models)],condition=segment,price=price,acquisition_cost=cost,vehicle_gross=price-cost,cash_at_sale=down,amount_financed=price-down,allocated_advertising=round(row['marketing_cost']/max(1,row['sales']),2)))
    return dict(label='Synthetic example sales register: one illustrative demand path, not actual transactions or the forecast average.',monthly=cash,deals=deals[:2000],total_deals=sum(int(r['sales']) for r in rows),truncated=sum(r['sales'] for r in rows)>2000)
