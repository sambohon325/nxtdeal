"""Existing Hub network transport, stricter than legacy fallback routes."""
from fastapi import APIRouter,Header
from pydantic import BaseModel,ConfigDict,Field
from core.dealership_lab import policy
router=APIRouter(prefix='/network/dealership-lab-policy',tags=['Hub Lab policy'])


class Update(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dealer_id:str=Field(min_length=1,max_length=100)
    enabled:bool=Field(strict=True)
    revision:int=Field(ge=0,strict=True)


@router.get('')
def get(dealer_id:str,network_key:str|None=Header(default=None,alias='X-NXTDeal-Network-Key')):
    policy.authorize(network_key,dealer_id)
    return policy.read()


@router.post('')
def put(body:Update,network_key:str|None=Header(default=None,alias='X-NXTDeal-Network-Key')):
    return policy.update(network_key,**body.model_dump())
