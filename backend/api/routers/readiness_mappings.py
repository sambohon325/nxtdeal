"""Audited configuration of the real CSV importer."""
from fastapi import APIRouter,Header,HTTPException
from pydantic import Field
from api.deps import _authenticate
from api.routers import sales_crm_advanced as store
from core.csv_mapping import REQUIRED,validate_mapping
router=APIRouter(prefix='/readiness/mappings',tags=['readiness mappings'])
def auth(header):
 p,e=_authenticate(header)
 if e:raise HTTPException(401,'Sign in to manage source mappings')
 if p['role'] not in {'ADMIN','OPERATIONS'}:raise HTTPException(403,'Admin or Operations access required')
 return p['employee_id']
class Mapping(store.Model):
 revision:int=Field(ge=0)
 columns:dict[str,str]
@router.get('')
def listing(authorization:str=Header(None)):
 auth(authorization)
 with store._lock:
  return {'connections':[{'id':e.id,'name':e.attributes['name'],'department':e.attributes['department'],'revision':e.attributes.get('mapping_revision',0),'columns':e.attributes.get('column_mapping',{}),'history':e.attributes.get('mapping_history',[])} for e in store.all_of('Connection') if e.attributes.get('connection_type')=='csv'],'required':REQUIRED}
@router.put('/{connection_id}')
def save(connection_id:str,body:Mapping,authorization:str=Header(None)):
 actor=auth(authorization)
 try:validate_mapping(body.columns)
 except ValueError as e:raise HTTPException(422,str(e))
 with store._lock,store.transaction():
  e=store.find(connection_id,'Connection');a=e.attributes
  if a.get('connection_type')!='csv':raise HTTPException(422,'Only CSV connections support header mappings')
  if a.get('mapping_revision',0)!=body.revision:raise HTTPException(409,'This mapping changed. Reload before saving.')
  a['column_mapping']=dict(body.columns);a['mapping_revision']=body.revision+1
  a.setdefault('mapping_history',[]).append({'at':store.now().isoformat(),'actor':actor,'columns':dict(body.columns),'revision':a['mapping_revision']})
  return {'revision':a['mapping_revision'],'columns':a['column_mapping']}
