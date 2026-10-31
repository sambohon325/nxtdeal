"""Bounded workspace review metadata across snapshot and creation-event batches."""
from collections import Counter
from core import dealer_bridge as bridge
from core.bridge_contracts import timestamp
from core.dealeros import ledger

STATES = frozenset({"pending","all","staged","validated","blocked","activated","cancelled"})
KINDS = {"BridgeJob":"snapshot", "BridgeEventJob":"event"}


def read(actor, system_id=None, status="pending", kind="all", limit=25, before_id=None):
    bridge.authorize(actor)
    if status not in STATES or kind not in {"all","snapshot","event"} or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Bounded review queue filters required")
    if before_id is not None and (not isinstance(before_id,str) or not 1 <= len(before_id) <= 120):
        raise ValueError("Use a review queue cursor from this source scope")
    with bridge.LOCK:
        if system_id is not None: bridge.get(system_id,"BridgeSystem")
        records = list(ledger.get_all().values())
        systems = {e.id:e.attributes for e in records if e.entity_type == "BridgeSystem" and e.attributes.get("workspace_id") == ledger.tenant.workspace_id}
        jobs = [e for e in records if e.entity_type in KINDS and e.attributes.get("workspace_id") == ledger.tenant.workspace_id
                and e.attributes.get("system_id") in systems and (system_id is None or e.attributes.get("system_id") == system_id)
                and (kind == "all" or KINDS[e.entity_type] == kind)]
        def order(entity): return timestamp(entity.attributes["created_at"]), entity.id
        anchor = None
        if before_id is not None:
            before = next((e for e in jobs if e.id == before_id),None)
            if before is None: raise ValueError("Review queue cursor does not belong to this source scope")
            anchor = order(before)
        counts = dict(Counter(e.attributes["status"] for e in jobs))
        wanted = {"staged","validated","blocked"} if status == "pending" else None if status == "all" else {status}
        matching = [e for e in jobs if wanted is None or e.attributes["status"] in wanted]
        eligible = sorted((e for e in matching if anchor is None or order(e) < anchor),key=order,reverse=True)
        page = eligible[:limit]
        summaries = []
        for e in page:
            value, source = e.attributes, systems[e.attributes["system_id"]]
            summaries.append({"id":e.id,"kind":KINDS[e.entity_type],"system_id":value["system_id"],
                "system_name":source["name"],"vendor":source["vendor"],"source_paused":bool(source.get("paused")),
                "status":value["status"],"created_at":value["created_at"],
                "review_advisory_rows":value.get("reconciliation",{}).get("review_advisory_rows") if e.entity_type == "BridgeJob" else None,
                "definition_id":value.get("mapping_id") if e.entity_type == "BridgeJob" else value.get("profile_id"),
                "row_count":value.get("payload_cleanup",{}).get("row_count",len(value.get("rows",[]))),
                "payload_removed":bool(value.get("payload_cleanup"))})
        return {"jobs":summaries,"status_counts":counts,"matching_jobs":len(matching),
            "next_before_id":page[-1].id if len(eligible) > len(page) else None,
            "filters":{"system_id":system_id,"status":status,"kind":kind},
            "systems":[{"id":key,"name":value["name"]} for key,value in sorted(systems.items(),key=lambda item:(item[1]["name"],item[0]))],
            "notice":"Live review metadata only. Counts can change as batches are reviewed. Cursor paging excludes newer entries; refresh for new work. No source row values, approvals or external calls are included."}
