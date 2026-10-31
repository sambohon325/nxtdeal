"""Consistency evidence for signed gateway staging, never a new approval."""
from core import dealer_bridge as bridge

TRANSPORT = "nxtdeal_adf_gateway_v1"


def checked(job_id, job):
    claimed = job.get("transport") == TRANSPORT or job.get("inbound_receipt_id") or job.get("created_principal") == "inbound_gateway"
    if not claimed: return None
    receipt_id = job.get("inbound_receipt_id")
    if job.get("transport") != TRANSPORT or not isinstance(receipt_id,str):
        raise ValueError("Signed delivery evidence is missing or changed")
    record = bridge.get(receipt_id,"BridgeInboundDelivery")
    if (record.get("checksum") != bridge.digest({key:value for key,value in record.items() if key != "checksum"}) or
            record.get("job_id") != job_id or record.get("system_id") != job.get("system_id") or
            record.get("profile_id") != job.get("profile_id") or record.get("profile_hash") != job.get("profile_hash") or
            record.get("body_hash") != job.get("source_evidence",{}).get("export_sha256") or
            record.get("authorized_by") != job.get("created_by") or job.get("created_principal") != "inbound_gateway" or
            record.get("transport") != TRANSPORT):
        raise ValueError("Signed delivery evidence is missing or changed")
    return {"status":"consistent", "receipt_id":receipt_id,
            **{key:record[key] for key in ("transport","binding_revision","environment","received_at","authorized_by","body_hash","delivery_id_hash","checksum")},
            "notice":"Retained evidence of verified gateway receipt, not human approval or proof of source accuracy. Signing material is not retained; this consistency check does not reverify the original signature."}
