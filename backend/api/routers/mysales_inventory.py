"""Read-only, opt-in retail inventory for independent MySales reps.
No staff authentication, customer records, cost, margin or internal notes.
"""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
router=APIRouter()

@router.get('/public/mysales/inventory')
def mysales_inventory(limit:int=Query(default=100,ge=1,le=500)):
    if os.getenv('NXTDEAL_MYSALES_INVENTORY_ENABLED')!='true':
        raise HTTPException(404,'This dealership has not enabled MySales inventory sharing.')
    from core.websites import get_live_inventory
    fields=('id','year','make','model','trim','price','mileage','image_url')
    items=[{k:row.get(k) for k in fields} for row in get_live_inventory(limit=limit)]
    return {'items':items,'as_of':datetime.now(timezone.utc).isoformat(),'read_only':True,'limit':limit}
