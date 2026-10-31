"""Floorplan source records and recorded external payoffs; never initiates a bank transfer."""
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Header, HTTPException
from pydantic import Field
from api.deps import _authenticate
from api.routers import sales_crm_advanced as store
from core.entities import Entity
router=APIRouter(prefix='/finance/floorplan-work',tags=['floorplan work'])
ACCOUNT='FloorplanAccount'
PAYOFF='FloorplanPayoff'
def auth(header,approval=False):
 p,e=_authenticate(header)
 if e:raise HTTPException(401,'Sign in to manage floorplan work')
 roles={'ADMIN','OPERATIONS','FINANCE'} if approval else {'ADMIN','OPERATIONS','FINANCE','INVENTORY'}
 if p['role'] not in roles:raise HTTPException(403,'Floorplan access required')
 return p['employee_id']
def amount(value):
 try:
  d=Decimal(str(value))
  if not d.is_finite() or d<=0 or d>Decimal('10000000') or d.as_tuple().exponent < -2:raise ValueError()
  return int(d*100)
 except (InvalidOperation,ValueError,TypeError):raise HTTPException(422,'Enter a positive amount with at most two decimal places')
def audit(e,actor,event,detail):
 e.attributes.setdefault('history',[]).append({'at':store.now().isoformat(),'actor':actor,'event':event,'detail':detail})
 e.attributes['revision']=e.attributes.get('revision',0)+1
def revision(e,value):
 if e.attributes['revision']!=value:raise HTTPException(409,'This record changed. Refresh before saving.')
class OpenAccount(store.Model):
 vehicle_id:str
 lender:str=Field(min_length=2,max_length=160)
 principal:str
 currency:Literal['USD','CAD']
 source_reference:str=Field(min_length=3,max_length=300)
class Request(store.Model):
 revision:int=Field(ge=1)
 amount:str
 evidence:str=Field(min_length=10,max_length=2000)
class Decision(store.Model):
 revision:int=Field(ge=1)
 action:Literal['approve','reject','record_payment']
 reference:str=Field(min_length=3,max_length=300)
 evidence:str=Field(min_length=10,max_length=2000)
class Title(store.Model):
 revision:int=Field(ge=1)
 status:Literal['lender_held','requested','released','received']
 evidence:str=Field(min_length=10,max_length=2000)
@router.get('')
def list_work(authorization:str=Header(None)):
 auth(authorization)
 with store._lock:
  vehicles=[{'id':e.id,'name':' '.join(str(e.attributes.get(k,'')) for k in ['Year','Make','Model'])+' '+str(e.attributes.get('VIN',''))} for e in store.ledger.get_all().values() if e.entity_type=='Vehicle']
  return {'accounts':[store.serial(e) for e in store.all_of(ACCOUNT)],'payoffs':[store.serial(e) for e in store.all_of(PAYOFF)],'vehicles':vehicles,'execution':'Records lender statements and externally completed payments. NXTDeal does not transfer funds.'}
@router.post('')
def open_account(body:OpenAccount,authorization:str=Header(None)):
 actor=auth(authorization);principal=amount(body.principal)
 with store._lock,store.transaction():
  store.find(body.vehicle_id,'Vehicle')
  if any(e.attributes['vehicle_id']==body.vehicle_id and e.attributes['balance_cents']>0 for e in store.all_of(ACCOUNT)):raise HTTPException(409,'This vehicle already has an open floorplan account')
  e=Entity('FLP-'+uuid4().hex,ACCOUNT,{'vehicle_id':body.vehicle_id,'lender':body.lender,'principal_cents':principal,'balance_cents':principal,'currency':body.currency,'source_reference':body.source_reference,'title_status':'lender_held','history':[]})
  audit(e,actor,'opened',body.source_reference);store.ledger.add_entity(e);return store.serial(e)
@router.post('/{account_id}/payoffs')
def request_payoff(account_id:str,body:Request,authorization:str=Header(None)):
 actor=auth(authorization);value=amount(body.amount)
 with store._lock,store.transaction():
  account=store.find(account_id,ACCOUNT);revision(account,body.revision)
  if value>account.attributes['balance_cents']:raise HTTPException(422,'Payoff exceeds the recorded outstanding balance')
  if any(e.attributes['account_id']==account_id and e.attributes['status'] in {'requested','approved'} for e in store.all_of(PAYOFF)):raise HTTPException(409,'Resolve the existing payoff request first')
  e=Entity('FPO-'+uuid4().hex,PAYOFF,{'account_id':account_id,'amount_cents':value,'currency':account.attributes['currency'],'status':'requested','requested_by':actor,'history':[]})
  audit(e,actor,'requested',body.evidence);store.ledger.add_entity(e);audit(account,actor,'payoff_requested',e.id);return store.serial(e)
@router.post('/payoffs/{payoff_id}/decision')
def decide(payoff_id:str,body:Decision,authorization:str=Header(None)):
 actor=auth(authorization,True)
 with store._lock,store.transaction():
  e=store.find(payoff_id,PAYOFF);revision(e,body.revision);a=e.attributes;account=store.find(a['account_id'],ACCOUNT)
  if body.action in {'approve','reject'}:
   if a['status']!='requested':raise HTTPException(409,'Only a requested payoff can receive a decision')
   if body.action=='approve' and a['requested_by']==actor:raise HTTPException(403,'A different authorized employee must approve this request')
   a['status']='approved' if body.action=='approve' else 'rejected'
  else:
   if a['status']!='approved':raise HTTPException(409,'Approve the request before recording an external payment')
   if a['amount_cents']>account.attributes['balance_cents']:raise HTTPException(409,'Outstanding balance changed; reconcile before recording payment')
   if any(x.attributes.get('bank_reference')==body.reference for x in store.all_of(PAYOFF)):raise HTTPException(409,'This bank reference has already been recorded')
   account.attributes['balance_cents']-=a['amount_cents'];a['status']='recorded';a['bank_reference']=body.reference
  audit(e,actor,body.action,body.reference+' — '+body.evidence);audit(account,actor,body.action,e.id);return store.serial(e)
@router.post('/{account_id}/title')
def update_title(account_id:str,body:Title,authorization:str=Header(None)):
 actor=auth(authorization)
 with store._lock,store.transaction():
  e=store.find(account_id,ACCOUNT);revision(e,body.revision)
  if body.status in {'released','received'} and e.attributes['balance_cents']>0:raise HTTPException(422,'Record full payoff before confirming title release')
  e.attributes['title_status']=body.status;audit(e,actor,'title_'+body.status,body.evidence);return store.serial(e)
