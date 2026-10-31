"""Planning earnings and BHPH cohort cash flows; not a loan servicing ledger."""
import math
import statistics
from datetime import datetime,timezone

DEFAULTS=dict(existing_term=30,repo_share=0,repo_balance=9000,repo_cost=650,repo_recon=800,repo_sale_fee=250,opening_receivables=0,opening_cash=0,financed_share=80,down_payment=2500,apr=18,term=30,collection_rate=95,monthly_default=1,recovery_rate=25,recovery_lag=3,funding_apr=8,other_expense=0,depreciation=0,capex=0,debt_principal=0,owner_draw=0,tax_rate=0)
LIMITS=dict(existing_term=(1,120),repo_share=(0,100),repo_balance=(1,100000),repo_cost=(0,10000),repo_recon=(0,10000),repo_sale_fee=(0,10000),opening_receivables=(0,1e9),opening_cash=(-1e9,1e9),financed_share=(0,100),down_payment=(0,100000),apr=(0,100),term=(1,120),collection_rate=(0,100),monthly_default=(0,100),recovery_rate=(0,100),recovery_lag=(0,36),funding_apr=(0,100),other_expense=(0,1e8),depreciation=(0,1e8),capex=(0,1e8),debt_principal=(0,1e8),owner_draw=(0,1e8),tax_rate=(0,100))
def settings(raw):
    if raw is None:raw={}
    if not isinstance(raw,dict):raise ValueError('Invalid earnings assumptions.')
    out={}
    for side in ('baseline','scenario'):
        supplied=raw.get(side,{})
        if not isinstance(supplied,dict):raise ValueError('Invalid cash-flow assumptions.')
        out[side]={}
        for key,default in DEFAULTS.items():
            v=supplied.get(key,default);lo,hi=LIMITS[key]
            if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('Invalid '+key.replace('_',' ')+'.')
            if key in ('term','existing_term','recovery_lag') and int(v)!=v:raise ValueError('Use whole months.')
            out[side][key]=v
    return out

def payment(balance,rate,term):return balance/term if rate==0 else balance*rate/(1-(1+rate)**(-term))

def cashflow(rows,e,side):
    p=e['finance'][side];bhph='BHPH' in e['dealership']['kind'];rate=p['apr']/1200
    loans=[]
    if bhph and p['opening_receivables']:loans.append([p['opening_receivables'],payment(p['opening_receivables'],rate,p['existing_term'])])
    recoveries={};repo_events={};cash=p['opening_cash'];out=[]
    for i,row in enumerate(rows):
        opening=sum(x[0] for x in loans);principal=interest=defaults=0
        for loan in loans:
            lost=loan[0]*p['monthly_default']/100;loan[0]-=lost;defaults+=lost
            scheduled_interest=loan[0]*rate
            paid=min(loan[0]+scheduled_interest,loan[1]*(1-p['monthly_default']/100))*p['collection_rate']/100
            interest_paid=min(scheduled_interest,paid);principal_paid=min(loan[0],max(0,paid-interest_paid))
            loan[0]-=principal_paid;loan[1]*=1-p['monthly_default']/100;principal+=principal_paid;interest+=interest_paid
        recoveries[i+int(p['recovery_lag'])]=recoveries.get(i+int(p['recovery_lag']),0)+defaults*p['recovery_rate']/100
        recovery=recoveries.get(i,0);credit_loss=defaults*(1-p['recovery_rate']/100)
        repos=defaults/p['repo_balance']*p['repo_share']/100 if bhph else 0
        repo_events[i+int(p['recovery_lag'])]=repo_events.get(i+int(p['recovery_lag']),0)+repos
        repo_expense=repos*p['repo_cost']+repo_events.get(i,0)*(p['repo_recon']+p['repo_sale_fee'])
        origin=row['used_sales']*max(0,e['segments']['used']['price']-p['down_payment'])*p['financed_share']/100 if bhph else 0
        if origin:loans.append([origin,payment(origin,rate,p['term'])])
        funding=opening*p['funding_apr']/1200 if bhph else 0
        pretax=row['contribution']+interest-credit_loss-funding-p['other_expense']-p['depreciation']-repo_expense
        tax=max(0,pretax)*p['tax_rate']/100
        # Inventory growth requires cash beyond cost of vehicles already sold.
        stock_cash=sum((row[k+'_arrivals']-row[k+'_sales'])*max(0,v['price']-v['gross']) for k,v in e['segments'].items())
        net_cash=row['contribution']-origin+principal+interest+recovery-funding-p['other_expense']-repo_expense-tax-stock_cash-p['capex']-p['debt_principal']-p['owner_draw']
        cash+=net_cash
        out.append(dict(repo_count=repos,repo_expense=repo_expense,vehicle_revenue=sum(row[k+'_sales']*v['price'] for k,v in e['segments'].items()),advertising=row.get('marketing_cost',0),inventory_purchases=sum(row[k+'_arrivals']*max(0,v['price']-v['gross']) for k,v in e['segments'].items()),down_payments=row['used_sales']*min(e['segments']['used']['price'],p['down_payment'])*p['financed_share']/100 if bhph else 0,month=i+1,profit=pretax-tax,pretax=pretax,tax=tax,net_cash=net_cash,cash_balance=cash,principal_collections=principal,interest_collections=interest,originations=origin,defaults=defaults,credit_loss=credit_loss,recoveries=recovery,receivables=sum(x[0] for x in loans),funding=funding,inventory_cash=stock_cash,contribution=row['contribution'],sales=row['sales']))
    return out



