"""New rewards-only session boundary; legacy simulated verification stays closed."""
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from core import loyalty_workflows as flow, loyalty_program as lp
from core.cors_policy import DEALER_WEB_ORIGINS
from api.routers.loyalty_program import staff, authorize, invoke, FULFILL, ADJUST

router=APIRouter()
COOKIE="nxtdeal_rewards"
PREFIX="/customer/loyalty"


def origin(request):
    allowed=set(DEALER_WEB_ORIGINS)
    allowed.update(x.strip() for x in os.environ.get("LOYALTY_CUSTOMER_ORIGINS", "").split(",") if x.strip())
    if request.headers.get("origin") not in allowed:
        raise HTTPException(403,detail="Open rewards from your dealership's approved app.")


def customer(request:Request):
    origin(request)
    csrf=request.headers.get("x-loyalty-csrf", "") if request.method not in {"GET","HEAD"} else None
    try:
        return flow.session(request.cookies.get(COOKIE),csrf)
    except lp.LoyaltyError as exc:
        raise HTTPException(401,detail=str(exc))


class StrictBody(BaseModel):
    model_config=ConfigDict(extra="forbid")


class Invitation(StrictBody):
    invitation:str=Field(min_length=32,max_length=200)


class Enrollment(StrictBody):
    request_key:str=Field(min_length=1,max_length=200)
    terms_version:str
    accepted:StrictBool


class Reserve(StrictBody):
    request_key:str=Field(min_length=1,max_length=200)
    reward_id:str
    appointment_id:str


class Release(StrictBody):
    request_key:str=Field(min_length=1,max_length=200)


class Preferences(StrictBody):
    promotions:StrictBool


class IdentityCheck(StrictBody):
    reason:str=Field(min_length=5,max_length=1000)


class Checkout(StrictBody):
    reservation_id:str|None=None


class Refund(StrictBody):
    refund_cents:StrictInt=Field(gt=0)
    reason:str=Field(min_length=1,max_length=1000)
    request_key:str=Field(min_length=1,max_length=200)


class Visit(StrictBody):
    scheduled_start:str
    location:str
    notes:str=Field(default="",max_length=1000)
    request_key:str=Field(min_length=1,max_length=200)


class PartsLink(StrictBody):
    source_id:str
    location:str="default"
    reason:str=Field(min_length=5,max_length=1000)


@router.post(PREFIX+"/session")
def accept(data:Invitation,request:Request,response:Response):
    origin(request)
    local=request.url.hostname in {"localhost","127.0.0.1","testserver"}
    if not local and request.url.scheme!="https":
        raise HTTPException(400,detail="Secure HTTPS is required.")
    token,result=invoke(flow.accept_invitation,data.invitation)
    response.set_cookie(COOKIE,token,max_age=43200,httponly=True,secure=not local,samesite="lax" if local else "none",path=PREFIX)
    response.headers["Cache-Control"]="no-store"
    return result


@router.get(PREFIX+"/session")
def current(response:Response,identity=Depends(customer)):
    response.headers["Cache-Control"]="no-store"
    return {"csrf":identity["csrf"],"expires_at":identity["expires_at"]}


@router.post(PREFIX+"/logout")
def logout(request:Request,response:Response,identity=Depends(customer)):
    with lp.transaction() as db:
        db.execute("UPDATE loyalty_sessions SET revoked=1 WHERE hash=?",(identity["hash"],))
    response.delete_cookie(COOKIE,path=PREFIX)
    return {"signed_out":True}


@router.get(PREFIX)
def view(response:Response,identity=Depends(customer)):
    response.headers["Cache-Control"]="no-store"
    return invoke(flow.customer_view,identity["customer_id"])


@router.post(PREFIX+"/enroll")
def enroll(data:Enrollment,identity=Depends(customer)):
    if not data.accepted:
        raise HTTPException(422,detail="Accept the current program terms to join.")
    entity=flow.customer_record(identity["customer_id"])
    with lp.transaction() as db:
        config=lp.active_program(db)
        if not config.get("terms","").strip():
            raise HTTPException(409,detail="Your dealership needs to publish the program terms before online enrollment.")
    name=entity.attributes.get("Name") or " ".join([entity.attributes.get("FirstName",""),entity.attributes.get("LastName","")]).strip() or entity.id
    return invoke(lp.enroll,entity.id,name,"customer:"+entity.id,"customer:"+entity.id+":"+data.request_key,
                  data.terms_version,legacy_points=entity.attributes.get("loyalty_points_balance",0))


@router.post(PREFIX+"/reserve")
def reserve(data:Reserve,identity=Depends(customer)):
    cid=identity["customer_id"]
    return invoke(flow.reserve_for_visit,cid,data.reward_id,data.appointment_id,"customer:"+cid,"customer:"+cid+":"+data.request_key)


@router.post(PREFIX+"/reservations/{hold_id}/release")
def release(hold_id:str,data:Release,identity=Depends(customer)):
    cid=identity["customer_id"]
    return invoke(lp.resolve_hold,cid,hold_id,"release","customer:"+cid,"customer:"+cid+":"+data.request_key)


@router.post(PREFIX+"/preferences")
def preferences(data:Preferences,identity=Depends(customer)):
    return flow.preferences(identity["customer_id"],data.promotions)


@router.post(PREFIX+"/appointments")
def request_visit(data:Visit,identity=Depends(customer)):
    return invoke(flow.request_visit,identity["customer_id"],data.scheduled_start,data.location,data.notes,data.request_key)


@router.post("/loyalty/program/members/{customer_id}/invitation")
def invite(customer_id:str,data:IdentityCheck,user=Depends(staff)):
    return invoke(flow.invite,customer_id,authorize(user,FULFILL),data.reason)


@router.post("/loyalty/program/members/{customer_id}/revoke-access")
def revoke(customer_id:str,user=Depends(staff)):
    return invoke(flow.revoke,customer_id,authorize(user,ADJUST))


@router.get("/loyalty/program/members/{customer_id}/connections")
def connections(customer_id:str,user=Depends(staff)):
    invoke(flow.customer_record,customer_id)
    with lp.transaction() as db:
        locations=lp.active_program(db).get("locations") or ["default"]
    return {"locations":locations,"permissions":{"fulfill":user.get("role") in FULFILL,"adjust":user.get("role") in ADJUST},"appointments":flow.appointments(customer_id),"transactions":flow.native_sources(customer_id),
            "unlinked_parts":[{"id":e.id,"label":str(e.attributes.get("SaleNumber",e.id))+" · "+str(e.attributes.get("PartNumber",""))}
                              for e in flow.ledger.get_all().values() if e.entity_type==flow.PART_SALE and not e.attributes.get("customer_id") and not e.attributes.get("CustomerID")][:100],
            "receipts":flow.customer_view(customer_id).get("receipts",[])}


@router.post("/loyalty/program/transactions/{source_id}/complete")
def complete(source_id:str,data:Checkout,user=Depends(staff)):
    return invoke(flow.complete_transaction,source_id,authorize(user,FULFILL),data.reservation_id)


@router.post("/loyalty/program/members/{customer_id}/parts-sale")
def link_parts(customer_id:str,data:PartsLink,user=Depends(staff)):
    return invoke(flow.link_parts_sale,data.source_id,customer_id,data.location,data.reason,authorize(user,FULFILL))


@router.post("/loyalty/program/transactions/{source_id}/refund")
def refund(source_id:str,data:Refund,user=Depends(staff)):
    return invoke(flow.refund,source_id,data.refund_cents,data.reason,data.request_key,authorize(user,ADJUST))


@router.post("/loyalty/program/reconcile")
def reconcile(user=Depends(staff)):
    authorize(user,ADJUST)
    return flow.reconcile()
