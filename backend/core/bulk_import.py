"""
Bulk Import with column mapping + dedupe (Bumper parity, 2026-07-25).

Bumper customers arrive with a book of contacts/loans in a spreadsheet and expect to
map their columns to the system's fields, preview what will land, and skip the people
who are already in here -- not re-key hundreds of rows or blindly double-load their
book. This module is that engine: parse a CSV, apply a caller-supplied column mapping,
dedupe against the existing graph (and within the same batch) by normalized
email/phone, and create real Lead/Customer entities through the canonical create paths
so an imported record is indistinguishable from a hand-entered one.

Two-phase by design, mirroring the on-demand posture used elsewhere (no hidden writes):
`plan_import` is non-destructive and returns exactly what `run_import` *would* do, so a
UI can show a preview ("312 new, 47 duplicates, 3 errors") before anyone commits. Leads
are created via core/lead_intake.create_lead (so ASSIGNED_TO / INTERESTED_IN wiring and
pipeline seeding happen), which is the same shape imports/lead_import.py's CSV path
writes -- we deliberately do NOT hand-roll raw dict(row) entities the way the seed
importers do, because that skips relationship wiring.
"""

import csv
import io

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD, VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.lead_intake import create_lead, VALID_SOURCES
from datetime import datetime, timezone


# Canonical target fields a mapping may point at. The UI shows these; the caller's
# mapping is {source_column_name: canonical_field}.
LEAD_FIELDS = ["first_name", "last_name", "email", "phone", "city", "state", "source", "vin"]
CUSTOMER_FIELDS = ["first_name", "last_name", "email", "phone", "city", "state"]
# Vehicle / inventory upload (Freemium roadmap Phase 3 -- the Foundation "Inventory Upload" made
# real, self-serve, credential-free). Dedupe is by VIN and stock number, not email/phone.
VEHICLE_FIELDS = ["vin", "stock_number", "year", "make", "model", "trim", "price", "mileage"]
TARGET_FIELDS = {"lead": LEAD_FIELDS, "customer": CUSTOMER_FIELDS, "vehicle": VEHICLE_FIELDS}

# A record needs at least a name AND a contact handle (email or phone) -- a row with no
# way to reach the person and no way to dedupe them is not worth importing.
REQUIRED_NAME = ["first_name", "last_name"]

# Guard against a pathological upload. A real dealer book is hundreds-to-low-thousands;
# past this we refuse rather than silently truncate (which would read as success). The
# ceiling is deliberately conservative because the canonical create path saves the graph
# per row, so a huge single import is better split into batches.
MAX_IMPORT_ROWS = 5000

DEFAULT_LEAD_SOURCE = "Website"

_EMAIL_KEYS = ("email", "Email", "email_address")
_PHONE_KEYS = ("phone", "Phone", "phone_number", "mobile", "cell")


def _normalize_email(value):
    return (value or "").strip().lower()


def _normalize_phone(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _entity_email(entity):
    for k in _EMAIL_KEYS:
        v = entity.attributes.get(k)
        if v:
            return v
    return ""


def _entity_phone(entity):
    for k in _PHONE_KEYS:
        v = entity.attributes.get(k)
        if v:
            return v
    return ""


def parse_csv(text):
    """Parse CSV text (already decoded to str) into (headers, rows). utf-8-sig handling
    is the caller's job on decode; DictReader tolerates a leading BOM in the first
    header if the text was decoded as plain utf-8, so we strip it defensively."""
    if text and text[0] == "﻿":
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    rows = []
    for r in reader:
        # DictReader yields OrderedDict; normalize to plain dict, drop the None key that
        # appears when a row has more columns than the header.
        rows.append({k: v for k, v in r.items() if k is not None})
    return headers, rows


def suggest_mapping(headers, target_type):
    """Best-effort auto-mapping: match each header to a canonical field by a normalized
    name comparison. The UI shows this as a starting point the user can correct."""
    fields = TARGET_FIELDS.get(target_type, [])
    # Synonyms -> canonical field. Keys are compared against a squashed header.
    synonyms = {
        "firstname": "first_name", "first": "first_name", "fname": "first_name", "givenname": "first_name",
        "lastname": "last_name", "last": "last_name", "lname": "last_name", "surname": "last_name", "familyname": "last_name",
        "email": "email", "emailaddress": "email", "e-mail": "email",
        "phone": "phone", "phonenumber": "phone", "mobile": "phone", "cell": "phone", "cellphone": "phone", "tel": "phone",
        "city": "city", "town": "city",
        "state": "state", "province": "state", "region": "state",
        "source": "source", "leadsource": "source", "origin": "source",
        "vin": "vin",
        # Vehicle / inventory columns
        "stock": "stock_number", "stocknumber": "stock_number", "stockno": "stock_number", "stock#": "stock_number",
        "year": "year", "modelyear": "year", "yr": "year",
        "make": "make", "manufacturer": "make",
        "model": "model",
        "trim": "trim", "trimlevel": "trim", "series": "trim",
        "price": "price", "askingprice": "price", "listprice": "price", "sellingprice": "price", "msrp": "price",
        "mileage": "mileage", "odometer": "mileage", "miles": "mileage", "kms": "mileage",
    }

    def squash(h):
        return "".join(ch for ch in (h or "").lower() if ch.isalnum())

    mapping = {}
    for h in headers:
        s = squash(h)
        canon = synonyms.get(s)
        if canon and canon in fields:
            mapping[h] = canon
    return mapping


def _apply_mapping(row, mapping):
    """mapping: {source_col: canonical_field}. Returns {canonical_field: trimmed value}."""
    out = {}
    for src, canon in (mapping or {}).items():
        if not canon:
            continue
        out[canon] = (str(row.get(src, "")) if row.get(src) is not None else "").strip()
    return out


def _existing_index():
    """Build {normalized_email -> id} and {normalized_phone -> id} across every existing
    Lead AND Customer, so an import dedupes against the whole contactable graph."""
    email_idx, phone_idx = {}, {}
    for e in ledger.get_all().values():
        if e.entity_type not in (CUSTOMER, LEAD):
            continue
        em = _normalize_email(_entity_email(e))
        ph = _normalize_phone(_entity_phone(e))
        if em:
            email_idx.setdefault(em, e.id)
        if ph:
            phone_idx.setdefault(ph, e.id)
    return email_idx, phone_idx


def _normalize_vin(value):
    return str(value or "").strip().upper()


def _normalize_stock(value):
    return str(value or "").strip().upper()


def _existing_vehicle_index():
    """{normalized_vin -> id} and {normalized_stock -> id} across existing Vehicles, so an inventory
    import dedupes against the lot the dealer already has."""
    vin_idx, stock_idx = {}, {}
    for e in ledger.get_all().values():
        if e.entity_type != VEHICLE:
            continue
        vin = _normalize_vin(e.attributes.get("VIN") or e.attributes.get("vin"))
        stock = _normalize_stock(e.attributes.get("StockNumber") or e.attributes.get("stock_number"))
        if vin:
            vin_idx.setdefault(vin, e.id)
        if stock:
            stock_idx.setdefault(stock, e.id)
    return vin_idx, stock_idx


def _validate_vehicle(record):
    """A vehicle row needs a way to identify + dedupe it: a VIN or a stock number. (Year/make/model
    can be backfilled from the VIN via the decoder, so they aren't required here.)"""
    errs = []
    if not record.get("vin") and not record.get("stock_number"):
        errs.append("no VIN or stock number (need at least one)")
    vin = _normalize_vin(record.get("vin"))
    if vin and len(vin) != 17:
        errs.append(f"VIN '{vin}' is not 17 characters")
    return errs


def _plan_vehicles(rows, mapping, dedupe=True):
    """Vehicle equivalent of _plan: classify each inventory row as create/duplicate/error, deduping
    by VIN then stock number against the lot and within the batch."""
    if not isinstance(rows, list):
        return None, {"error": "rows must be a list"}
    if len(rows) > MAX_IMPORT_ROWS:
        return None, {"error": f"too many rows ({len(rows)}); max {MAX_IMPORT_ROWS} per import"}

    vin_idx, stock_idx = _existing_vehicle_index() if dedupe else ({}, {})
    seen_vin, seen_stock = {}, {}

    verdicts = []
    for i, row in enumerate(rows):
        record = _apply_mapping(row, mapping)
        errs = _validate_vehicle(record)
        if errs:
            verdicts.append({"index": i, "status": "error", "errors": errs, "record": record})
            continue

        vin = _normalize_vin(record.get("vin"))
        stock = _normalize_stock(record.get("stock_number"))

        dup_of = None
        if dedupe:
            if vin and vin in vin_idx:
                dup_of = {"match": vin_idx[vin], "on": "vin"}
            elif stock and stock in stock_idx:
                dup_of = {"match": stock_idx[stock], "on": "stock_number"}
            elif vin and vin in seen_vin:
                dup_of = {"match": f"row {seen_vin[vin]}", "on": "vin (within import)"}
            elif stock and stock in seen_stock:
                dup_of = {"match": f"row {seen_stock[stock]}", "on": "stock_number (within import)"}

        if dup_of:
            verdicts.append({"index": i, "status": "duplicate", "duplicate_of": dup_of, "record": record})
            continue

        if vin:
            seen_vin[vin] = i
        if stock:
            seen_stock[stock] = i
        verdicts.append({"index": i, "status": "create", "record": record})

    return verdicts, None


def _create_vehicle(record, created_by, auto_decode=True):
    """Create a Vehicle from an import row. Registers the VIN business key so registry.find_vehicle
    works, then (best-effort) backfills Year/Make/Model/Trim from the VIN via the offline decoder --
    no network needed, so an inventory upload with just VINs still lands usable vehicles."""
    veh_id = id_generator.generate("VEH")
    attributes = {
        "VIN": _normalize_vin(record.get("vin")),
        "StockNumber": _normalize_stock(record.get("stock_number")),
        "Year": record.get("year", ""),
        "Make": record.get("make", ""),
        "Model": record.get("model", ""),
        "Trim": record.get("trim", ""),
        "Price": record.get("price", ""),
        "Mileage": record.get("mileage", ""),
        "Source": "Import",
        "CreatedBy": created_by,
        "CreatedAt": datetime.now(timezone.utc).isoformat(),
    }
    entity = Entity(id=veh_id, entity_type=VEHICLE, attributes=attributes)
    ledger.add_entity(entity)
    if attributes["VIN"]:
        try:
            registry.register_vehicle(attributes["VIN"], veh_id)
        except Exception:
            pass
    if auto_decode and attributes["VIN"]:
        try:
            from core.vin_decoder import apply_decode_to_vehicle
            # Offline decode only (no outbound network in-process); saves are batched by run_import.
            apply_decode_to_vehicle(veh_id, created_by, attempt_live=False, _skip_save=True)
        except Exception:
            pass
    return entity


def _resolve_source(record):
    src = (record.get("source") or "").strip()
    # An imported source only survives if it's one this system understands; anything
    # else (a Bumper-internal source label) falls back to the default rather than
    # polluting VALID_SOURCES-driven dashboards with unknown values.
    return src if src in VALID_SOURCES else DEFAULT_LEAD_SOURCE


def _validate(record, target_type):
    errs = []
    for f in REQUIRED_NAME:
        if not record.get(f):
            errs.append(f"missing {f}")
    if not record.get("email") and not record.get("phone"):
        errs.append("no email or phone (need at least one)")
    if record.get("email"):
        em = record["email"]
        if "@" not in em or em.startswith("@") or em.endswith("@"):
            errs.append(f"invalid email '{em}'")
    return errs


def _plan(rows, mapping, target_type, dedupe=True):
    """Shared core of plan_import/run_import: walk the rows once, classify each as
    creatable / duplicate / error. Returns a list of per-row verdicts plus the indexes,
    so run_import can act on the exact same decisions plan_import previewed."""
    if target_type not in TARGET_FIELDS:
        return None, {"error": f"target_type must be one of {list(TARGET_FIELDS)}"}
    # Vehicles dedupe/validate by VIN + stock number, not name + email/phone -- separate path so the
    # tested lead/customer logic below is unchanged.
    if target_type == "vehicle":
        return _plan_vehicles(rows, mapping, dedupe=dedupe)
    if not isinstance(rows, list):
        return None, {"error": "rows must be a list"}
    if len(rows) > MAX_IMPORT_ROWS:
        return None, {"error": f"too many rows ({len(rows)}); max {MAX_IMPORT_ROWS} per import"}

    email_idx, phone_idx = _existing_index() if dedupe else ({}, {})
    seen_email, seen_phone = {}, {}  # within-batch dedupe

    verdicts = []
    for i, row in enumerate(rows):
        record = _apply_mapping(row, mapping)
        errs = _validate(record, target_type)
        if errs:
            verdicts.append({"index": i, "status": "error", "errors": errs, "record": record})
            continue

        em = _normalize_email(record.get("email"))
        ph = _normalize_phone(record.get("phone"))

        dup_of = None
        if dedupe:
            if em and em in email_idx:
                dup_of = {"match": email_idx[em], "on": "email"}
            elif ph and ph in phone_idx:
                dup_of = {"match": phone_idx[ph], "on": "phone"}
            elif em and em in seen_email:
                dup_of = {"match": f"row {seen_email[em]}", "on": "email (within import)"}
            elif ph and ph in seen_phone:
                dup_of = {"match": f"row {seen_phone[ph]}", "on": "phone (within import)"}

        if dup_of:
            verdicts.append({"index": i, "status": "duplicate", "duplicate_of": dup_of, "record": record})
            continue

        if em:
            seen_email[em] = i
        if ph:
            seen_phone[ph] = i
        verdicts.append({"index": i, "status": "create", "record": record})

    return verdicts, None


def plan_import(rows, mapping, target_type, dedupe=True):
    """Non-destructive preview. Returns counts + per-row verdicts; writes nothing."""
    verdicts, err = _plan(rows, mapping, target_type, dedupe=dedupe)
    if err:
        return err
    counts = {"create": 0, "duplicate": 0, "error": 0}
    for v in verdicts:
        counts[v["status"]] += 1
    return {
        "target_type": target_type,
        "total": len(verdicts),
        "will_create": counts["create"],
        "duplicates": counts["duplicate"],
        "errors": counts["error"],
        "verdicts": verdicts,
    }


def _create_customer(record, created_by):
    """Minimal Customer create for import. Matches the capitalized attribute shape the
    CSV customer importer uses so downstream dashboards read it, and registers a business
    key so registry.find_customer works."""
    cust_id = id_generator.generate("CUST")
    attributes = {
        "CustomerID": cust_id,
        "FirstName": record.get("first_name", ""),
        "LastName": record.get("last_name", ""),
        "Email": record.get("email", ""),
        "Phone": record.get("phone", ""),
        "City": record.get("city", ""),
        "State": record.get("state", ""),
        "Source": "Import",
        "CreatedBy": created_by,
        "CreatedAt": datetime.now(timezone.utc).isoformat(),
    }
    entity = Entity(id=cust_id, entity_type=CUSTOMER, attributes=attributes)
    ledger.add_entity(entity)
    registry.register_customer(cust_id, cust_id)
    return entity


def run_import(rows, mapping, target_type, created_by, dedupe=True):
    """Commit an import. Creates a Lead/Customer for every 'create' verdict, skips
    duplicates and errors (reporting both), and saves the graph once at the end."""
    verdicts, err = _plan(rows, mapping, target_type, dedupe=dedupe)
    if err:
        return err

    created, skipped, errors = [], [], []
    for v in verdicts:
        if v["status"] == "error":
            errors.append({"index": v["index"], "errors": v["errors"]})
            continue
        if v["status"] == "duplicate":
            skipped.append({"index": v["index"], "duplicate_of": v["duplicate_of"]})
            continue
        rec = v["record"]
        try:
            if target_type == "lead":
                entity = create_lead(
                    created_by,
                    rec.get("first_name", ""),
                    rec.get("last_name", ""),
                    _resolve_source(rec),
                    phone=rec.get("phone") or None,
                    email=rec.get("email") or None,
                    city=rec.get("city") or None,
                    state=rec.get("state") or None,
                    vin=rec.get("vin") or None,
                )
            elif target_type == "vehicle":
                entity = _create_vehicle(rec, created_by)
            else:
                entity = _create_customer(rec, created_by)
            created.append(entity.id)
        except Exception as exc:  # a single bad row must not abort the whole import
            errors.append({"index": v["index"], "errors": [f"create failed: {exc}"]})

    save_graph(GRAPH_PATH)
    return {
        "target_type": target_type,
        "created": created,
        "created_count": len(created),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "errors": errors,
        "error_count": len(errors),
    }
