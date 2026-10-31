"""Readiness policy and explicitly approved forecast activation."""
from typing import Literal
from fastapi import APIRouter,Header,HTTPException
from pydantic import Field
from api.deps import _authenticate
from api.routers import sales_crm_advanced as store
from core.entities import Entity
from core.prediction import DEPARTMENTS,department_readiness
router=APIRouter(prefix='/readiness/policies',tags=['readiness policies'])
def auth(header,write=False):
 p,e=_authenticate(header)
 if e:raise HTTPException(401,'Sign in to review readiness')
 if write and p['role'] not in {'ADMIN','OPERATIONS'}:raise HTTPException(403,'Admin or Operations access required')
 return p['employee_id']
class Change(store.Model):
 revision:int=Field(ge=0)
 action:Literal['set_threshold','activate','pause']
 threshold:float=Field(default=90,ge=50,le=100,allow_inf_nan=False)
 evidence:str=Field(min_length=10,max_length=2000)
def policy(d):
 e=store.ledger.get_entity('READINESS-'+d)
 return {**department_readiness(d),'revision':e.attributes.get('revision',0) if e else 0,'history':e.attributes.get('history',[]) if e else []}
@router.get('')
def listing(authorization:str=Header(None)):
 auth(authorization)
 with store._lock:return {'departments':[policy(d) for d in DEPARTMENTS]}
@router.post('/{department}')
def update(department:str,body:Change,authorization:str=Header(None)):
 actor=auth(authorization,True)
 if department not in DEPARTMENTS:raise HTTPException(404,'Unknown forecast department')
 with store._lock,store.transaction():
  e=store.ledger.get_entity('READINESS-'+department)
  if e is None:e=Entity('READINESS-'+department,'ReadinessPolicy',{'department':department,'threshold':90,'enabled':False,'revision':0,'history':[]});store.ledger.add_entity(e)
  a=e.attributes
  if a['revision']!=body.revision:raise HTTPException(409,'Readiness policy changed. Refresh before saving.')
  observed=department_readiness(department)
  if body.action=='activate':
   if not observed['ready'] or observed['basis']=='industry_estimate':raise HTTPException(422,'Measured confidence and ledger coverage must meet the threshold before activation')
   a['enabled']=True
  elif body.action=='pause':a['enabled']=False
  else:a['threshold']=body.threshold;a['enabled']=False
  a['revision']+=1;a['history'].append({'at':store.now().isoformat(),'actor':actor,'action':body.action,'evidence':body.evidence,'confidence_pct':observed['confidence_pct'],'threshold':a['threshold']})
  return policy(department)
