"""Recorded pay plans and commission approvals. Never submits payroll or transfers money."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Header, HTTPException
from pydantic import Field
from api.deps import _authenticate
from api.routers import sales_crm_advanced as store
from core.entities import Entity
router=APIRouter(prefix='/finance/commission-work',tags=['commission work'])
PLAN='CommissionPayPlan';ITEM='CommissionApproval'
def auth(header):
 p,e=_authenticate(header)
 if e:raise HTTPException(401,'Sign in to manage commissions')
 if p['role'] not in {'ADMIN','OPERATIONS','FINANCE'}:raise HTTPException(403,'Finance access required')
 return p['employee_id']
def decimal(value,maximum):
 try:
  d=Decimal(str(value))
  if not d.is_finite() or d<0 or d>maximum or d.as_tuple().exponent < -2:raise ValueError()
  return d
 except (InvalidOperation,ValueError,TypeError):raise HTTPException(422,'Enter a valid non-negative amount with at most two decimal places')
def audit(e,actor,event,detail):
 e.attributes.setdefault('history',[]).append({'at':store.now().isoformat(),'actor':actor,'event':event,'detail':detail});e.attributes['revision']=e.attributes.get('revision',0)+1
class Plan(store.Model):
 name:str=Field(min_length=2,max_length=100)
 percent:str
 flat_amount:str
 currency:Literal['USD','CAD']
 policy_reference:str=Field(min_length=3,max_length=300)
class Claim(store.Model):
 plan_id:str
 deal_id:str
 employee_id:str
 approved_basis:str
 basis_evidence:str=Field(min_length=10,max_length=2000)
class Decision(store.Model):
 revision:int=Field(ge=1)
 action:Literal['approve','reject','record_paid','void']
 evidence:str=Field(min_length=10,max_length=2000)
 reference:str=Field(min_length=3,max_length=300)
@router.get('')
def listing(authorization:str=Header(None)):
 auth(authorization)
 with store._lock:
  choices=lambda kind:[{'id':e.id,'name':e.attributes.get('Name') or e.attributes.get('name') or e.id} for e in store.all_of(kind) if kind!='Deal' or e.attributes.get('status')=='funded']
  return {'plans':[store.serial(e) for e in store.all_of(PLAN)],'commissions':[store.serial(e) for e in store.all_of(ITEM)],'employees':choices('Employee'),'deals':choices('Deal')}
@router.post('/plans')
def create_plan(body:Plan,authorization:str=Header(None)):
 actor=auth(authorization);rate=decimal(body.percent,100);flat=decimal(body.flat_amount,10000000)
 with store._lock,store.transaction():
  e=Entity('CPP-'+uuid4().hex,PLAN,{'name':body.name,'percent':str(rate),'flat_cents':int(flat*100),'currency':body.currency,'policy_reference':body.policy_reference})
  audit(e,actor,'created',body.policy_reference);store.ledger.add_entity(e);return store.serial(e)
@router.post('')
def create_commission(body:Claim,authorization:str=Header(None)):
 actor=auth(authorization);basis=decimal(body.approved_basis,10000000)
 with store._lock,store.transaction():
  plan=store.find(body.plan_id,PLAN);deal=store.find(body.deal_id,'Deal');store.find(body.employee_id,'Employee')
  if deal.attributes.get('status')!='funded':raise HTTPException(422,'Commissions require a recorded funded deal')
  if any(e.attributes['deal_id']==body.deal_id and e.attributes['employee_id']==body.employee_id and e.attributes['status'] not in {'rejected','void'} for e in store.all_of(ITEM)):raise HTTPException(409,'This employee already has a commission for that deal')
  total=(basis*Decimal(plan.attributes['percent'])/100+Decimal(plan.attributes['flat_cents'])/100).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
  e=Entity('COM-'+uuid4().hex,ITEM,{'deal_id':body.deal_id,'employee_id':body.employee_id,'plan_id':body.plan_id,'plan_snapshot':dict(plan.attributes),'basis_cents':int(basis*100),'basis_evidence':body.basis_evidence,'amount_cents':int(total*100),'currency':plan.attributes['currency'],'status':'requested','requested_by':actor})
  audit(e,actor,'requested',body.basis_evidence);store.ledger.add_entity(e);return store.serial(e)
@router.post('/{item_id}/decision')
def decide(item_id:str,body:Decision,authorization:str=Header(None)):
 actor=auth(authorization)
 with store._lock,store.transaction():
  e=store.find(item_id,ITEM);a=e.attributes
  if a['revision']!=body.revision:raise HTTPException(409,'This commission changed. Refresh before saving.')
  permitted={'approve':{'requested'},'reject':{'requested'},'record_paid':{'approved'},'void':{'requested','approved'}}
  if a['status'] not in permitted[body.action]:raise HTTPException(409,'This action is not available in the current status')
  if body.action in {'approve','record_paid'} and store.find(a['deal_id'],'Deal').attributes.get('status')!='funded':raise HTTPException(409,'The deal is no longer funded; review the commission')
  if body.action=='approve' and (actor==a['requested_by'] or actor==a['employee_id']):raise HTTPException(403,'A different authorized employee must approve the commission')
  if body.action=='record_paid':
   if any(x.attributes.get('payment_reference')==body.reference for x in store.all_of(ITEM)):raise HTTPException(409,'This payment reference is already recorded')
   a['payment_reference']=body.reference
  a['status']={'approve':'approved','reject':'rejected','record_paid':'paid','void':'void'}[body.action];audit(e,actor,body.action,body.reference+' — '+body.evidence);return store.serial(e)
