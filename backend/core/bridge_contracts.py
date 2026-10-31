"""Vendor-neutral v1 records. No vendor names or executable mapping expressions."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Protocol

# Existing graph types and field conventions; new domains remain explicit graph types.
FIELDS = {
    "Dealer": "name", "Location": "name address dealer_id", "Employee": "first_name last_name department location_id",
    "Customer": "first_name last_name email phone location_id household_id", "Household": "name",
    "Vehicle": "vin year make model price currency status location_id", "Lead": "first_name last_name email phone status source",
    "Deal": "status customer_id vehicle_id amount currency location_id",
    "FinanceContract": "customer_id vehicle_id lender_name status currency principal down_payment installment_amount annual_percentage_rate term_months starts_at",
    "LoanAccount": "customer_id contract_id currency principal balance past_due_amount scheduled_payment status opened_at closed_at next_due_at",
    "PaymentSchedule": "account_id due_at amount currency principal_amount interest_amount fee_amount status",
    "Payment": "account_id paid_at amount currency principal_amount interest_amount fee_amount payment_method reverses_payment_id status",
    "CollectionCase": "account_id status days_past_due past_due_amount currency last_contact_at next_action_at", "Repossession": "account_id vehicle_id status occurred_at",
    "ServiceRecord": "customer_id vehicle_id status description location_id", "Appointment": "customer_id starts_at status location_id",
    "ServiceOperation": "service_id description amount currency", "Part": "name part_number quantity",
    "JournalEntry": "account_code ledger_account_id journal_id entry_side amount currency occurred_at description",
    "AccountingAccount": "name account_code account_type currency status",
    "Communication": "customer_id channel direction occurred_at", "Campaign": "name status",
    "Consent": "customer_id channel status occurred_at", "Ownership": "customer_id vehicle_id starts_at ends_at",
    "InventoryPrice": "vehicle_id price currency occurred_at",
}
FIELDS = {key: tuple(value.split()) for key, value in FIELDS.items()}
REQUIRED = {
    "Vehicle": {"vin"}, "LoanAccount": {"customer_id", "currency", "balance"},
    "PaymentSchedule": {"account_id", "due_at", "amount", "currency"},
    "Payment": {"account_id", "paid_at", "amount", "currency"},
    "CollectionCase": {"account_id", "status"}, "Repossession": {"account_id", "vehicle_id", "status"},
    "JournalEntry": {"account_code", "amount", "currency", "occurred_at"},
    "Consent": {"customer_id", "channel", "status", "occurred_at"},
}
REFERENCE_TYPES = {"dealer_id": "Dealer", "location_id": "Location", "household_id": "Household", "customer_id": "Customer", "vehicle_id": "Vehicle", "account_id": "LoanAccount", "contract_id": "FinanceContract", "service_id": "ServiceRecord", "reverses_payment_id": "Payment", "ledger_account_id": "AccountingAccount"}
# Native financial and campaign records have executable lifecycles. Imported
# facts retain their canonical kind without entering those workflows merely
# because a source status says "approved", "contract", "funded" or "active".
OBSERVATION_STORAGE_TYPES = {"Payment": "ImportedPayment", "FinanceContract": "ImportedFinanceContract",
                             "Deal": "ImportedDeal", "Campaign": "ImportedCampaign", "Consent": "ImportedConsent"}


def storage_kind(kind):
    return OBSERVATION_STORAGE_TYPES.get(kind, kind)


# Internal legacy graph aliases, not vendor field names. Preserve old dashboards.
GRAPH_ALIASES = {
    "Customer": {"first_name": "FirstName", "last_name": "LastName", "email": "Email", "phone": "Phone"},
    "Vehicle": {"vin": "VIN", "year": "Year", "make": "Make", "model": "Model", "price": "Price", "status": "Status"},
    "Lead": {"first_name": "FirstName", "last_name": "LastName", "email": "Email", "phone": "Phone", "status": "Status", "source": "Source"},
    "Employee": {"first_name": "FirstName", "last_name": "LastName", "department": "Department"},
}

def graph_values(kind, values):
    return {**values, **{alias: values[field] for field, alias in GRAPH_ALIASES.get(kind, {}).items() if field in values}}

MONEY = {"price", "amount", "principal", "balance", "down_payment", "installment_amount", "past_due_amount", "scheduled_payment", "principal_amount", "interest_amount", "fee_amount"}
DECIMAL_FIELDS = MONEY | {"annual_percentage_rate"}
INTEGER_FIELDS = {"year", "days_past_due", "term_months"}
LOOKUP_FIELDS = frozenset({"status", "channel", "direction", "payment_method", "account_type", "department", "entry_side", "currency"})
TRANSFORM_VERSION = 3
CONNECTOR_CAPABILITIES = frozenset({"authenticate", "discover", "schema", "history", "sync", "subscribe", "write", "reconcile", "health"})


def validated_capabilities(adapter):
    """Validate declarations without calling a vendor or resolving credentials.

    This verifies the local contract, not vendor access or semantic correctness.
    A bounded immutable result can be pinned to a reviewed runtime binding.
    """
    declared = getattr(adapter, "capabilities", None)
    if not isinstance(declared, (set, frozenset, list, tuple)) or len(declared) > len(CONNECTOR_CAPABILITIES):
        raise ValueError("Connector capabilities must be a bounded collection")
    if any(not isinstance(value, str) or value not in CONNECTOR_CAPABILITIES for value in declared):
        raise ValueError("Unknown connector capability")
    capabilities = frozenset(declared)
    if len(capabilities) != len(declared):
        raise ValueError("Duplicate connector capability")
    for capability in capabilities:
        method = getattr(adapter, capability, None)
        if not callable(method) or getattr(method, "bridge_unavailable", False):
            raise ValueError("Declared connector capability has no implementation")
    return capabilities

@dataclass(frozen=True)
class SourceRecord:
    object_type: str
    external_id: str
    modified_at: str
    values: dict

@dataclass(frozen=True)
class SourceEvent:
    """Explicit event time for adapters whose data is not a mutable snapshot.

    Deliberately not a SourceRecord: snapshot collection cannot silently treat
    creation/occurrence time as modified_at. Event staging requires its own
    reviewed ingestion profile before these drafts can enter the graph.
    """
    object_type: str
    external_id: str
    occurred_at: str
    source_namespace: str
    time_semantics: str
    values: dict

    def __post_init__(self):
        if not isinstance(self.time_semantics, str) or self.time_semantics not in {"created", "occurred"}:
            raise ValueError("Explicit creation or occurrence semantics required")
        for value, limit in ((self.object_type, 120), (self.external_id, 500), (self.source_namespace, 120)):
            if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > limit or any(ord(char) < 32 for char in value):
                raise ValueError("Bounded event source identity required")
        source_timestamp(self.occurred_at)
        if not isinstance(self.values, dict) or not 1 <= len(self.values) <= 100:
            raise ValueError("Bounded event values required")
        if any(not isinstance(key, str) or not key or len(key) > 120 or
               not isinstance(value, str) or len(value) > 100000 or "\x00" in value
               for key, value in self.values.items()):
            raise ValueError("Event values must be bounded named text fields")
        try:
            text_values = [self.object_type, self.external_id, self.source_namespace, self.occurred_at, *self.values.keys(), *self.values.values()]
            if sum(len(value.encode("utf-8")) for value in text_values) > 1_000_000:
                raise ValueError("Event text exceeds 1 MB")
        except UnicodeEncodeError:
            raise ValueError("Event fields must contain valid UTF-8 text") from None


@dataclass(frozen=True)
class SyncPage:
    records: tuple[SourceRecord, ...]
    cursor: str | None
    complete: bool

class Connector(Protocol):
    capabilities: frozenset[str]
    def authenticate(self, secret_reference: str): ...
    def discover(self): ...
    def schema(self, object_type: str): ...
    def history(self, object_type: str, cursor: str | None) -> SyncPage: ...
    def sync(self, object_type: str, cursor: str | None) -> SyncPage: ...
    def subscribe(self, callback_reference: str): ...
    def write(self, approved_command: dict): ...
    def reconcile(self, object_type: str): ...
    def health(self): ...

def decimal_value(value, *, max_integer_digits=24):
    # Bounded fixed-point values prevent non-finite amounts and exponent/precision
    # abuse, while preserving up to six fractional digits without float rounding.
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)) or len(str(value)) > 64:
        raise ValueError("Money must be a bounded decimal string or integer")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid money") from exc
    if not number.is_finite() or number.adjusted() >= max_integer_digits or number.as_tuple().exponent < -6:
        raise ValueError("Money exceeds supported precision or magnitude")
    return format(number, "f")


def timestamp(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("Bounded ISO source timestamp required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid ISO source timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    try:
        parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ValueError("Source timestamp is outside the supported UTC range") from None
    return parsed

class SourceTimePrecisionError(ValueError):
    pass


def source_timestamp(value):
    """Reject lossy precision at intake; retained history keeps its old parser."""
    parsed = timestamp(value)
    if any(any(digit != "0" for digit in fraction[6:]) for fraction in re.findall(r"[.,]([0-9]+)", value)):
        raise SourceTimePrecisionError("Source timestamps finer than microsecond precision require a dedicated adapter contract")
    offset_fraction = re.search(r"[+-]0{2}(?::?0{2}){0,2}[.,]([0-9]+)$", value)
    if offset_fraction and any(digit != "0" for digit in offset_fraction[1]) and parsed.utcoffset().total_seconds() == 0:
        raise SourceTimePrecisionError("Source timezone offset loses precision; a dedicated adapter contract is required")
    return parsed


def validate_mapping_spec(target, spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("source"), str) or not spec["source"].strip() or len(spec["source"]) > 120:
        raise ValueError("Invalid source column")
    if spec.get("transform") == "lookup":
        translations = spec.get("values")
        if (target not in LOOKUP_FIELDS or set(spec) != {"source", "transform", "values"} or
                not isinstance(translations, dict) or not 1 <= len(translations) <= 100 or
                any(not isinstance(value, str) or not value or value != value.strip() or len(value) > 120 or
                    any(ord(char) < 32 for char in value)
                    for pair in translations.items() for value in pair)):
            raise ValueError("Value lookup requires an eligible field and 1 to 100 exact bounded text translations")
    elif spec.get("transform") == "external_id":
        if (target not in REFERENCE_TYPES or set(spec) != {"source", "transform", "object_type"} or
                not isinstance(spec["object_type"], str) or not spec["object_type"].strip() or spec["object_type"] != spec["object_type"].strip() or len(spec["object_type"]) > 120):
            raise ValueError("External reference requires a relationship field and source object")
    elif set(spec) != {"source", "transform"} or spec.get("transform") not in {"text", "lower", "upper", "decimal", "integer"}:
        raise ValueError("Unsupported mapping transform")
    if spec.get("transform") == "integer" and target not in INTEGER_FIELDS | {"quantity"}:
        raise ValueError("Integer transformation requires an integer canonical field")


def transform(kind, mapping, values, *, version=TRANSFORM_VERSION):
    if type(version) is not int or version not in {1, 2, 3}:
        raise ValueError("Unsupported transformation version")
    if kind not in FIELDS or not mapping or set(mapping) - set(FIELDS[kind]):
        raise ValueError("Unknown canonical fields")
    result = {}
    for target, spec in mapping.items():
        validate_mapping_spec(target, spec)
        if spec["transform"] == "lookup" and version < 3:
            raise ValueError("Value lookup requires transformation version 3")
        value = values.get(spec["source"])
        if value is None or not str(value).strip():
            continue
        if version >= 2 and (target in DECIMAL_FIELDS or spec["transform"] == "decimal") and isinstance(value, (float, bool)):
            raise ValueError("Money must be a decimal string or integer")
        value = str(value).strip()
        op = spec["transform"]
        if op == "lookup":
            if value not in spec["values"]:
                raise ValueError("Source value has no approved translation")
            value = spec["values"][value]
        if op in {"lower", "upper"}:
            value = getattr(value, op)()
        if op == "integer" or version >= 2 and target in INTEGER_FIELDS:
            if not re.fullmatch(r"[+-]?\d{1,10}", value, flags=re.ASCII):
                raise ValueError("Invalid bounded integer")
            value = int(value)
            if not -(2**31) <= value < 2**31:
                raise ValueError("Integer exceeds supported range")
            if target == "year" and not 1000 <= value <= 9999:
                raise ValueError("Vehicle year must contain four digits")
            if target in {"days_past_due", "term_months"} and value < 0:
                raise ValueError("Days past due and term months cannot be negative")
        if op == "decimal" or target in DECIMAL_FIELDS:
            value = decimal_value(value)
        if target.endswith("_at"):
            parsed = timestamp(value)
            if version >= 2:
                value = parsed.astimezone(timezone.utc).isoformat()
        result[target] = value
    if not result:
        raise ValueError("No mapped values")
    if "email" in result:
        result["email"] = result["email"].lower()
        if len(result["email"]) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+", result["email"]):
            raise ValueError("Invalid email")
    if "vin" in result:
        result["vin"] = result["vin"].upper()
        if len(result["vin"]) != 17 or any(c not in "0123456789ABCDEFGHJKLMNPRSTUVWXYZ" for c in result["vin"]):
            raise ValueError("Invalid VIN")
    if REQUIRED.get(kind, set()) - set(result):
        raise ValueError("Missing required canonical fields")
    if kind == "Customer" and not any(result.get(f) for f in ("first_name", "last_name", "email", "phone")):
        raise ValueError("Customer identity required")
    if "currency" in result:
        result["currency"] = result["currency"].upper()
        if len(result["currency"]) != 3 or not result["currency"].isascii() or not result["currency"].isalpha():
            raise ValueError("Three-letter currency code required")
    allocations = {"principal_amount", "interest_amount", "fee_amount"}
    if kind == "JournalEntry" and "entry_side" in result:
        result["entry_side"] = result["entry_side"].lower()
        if result["entry_side"] not in {"debit", "credit"}:
            raise ValueError("Journal side must be debit or credit")
        if Decimal(result["amount"]) < 0:
            raise ValueError("Journal lines with an explicit side require a nonnegative amount")
    if "journal_id" in result and len(result["journal_id"]) > 500:
        raise ValueError("Journal identity exceeds the supported length")
    if kind in {"Payment", "PaymentSchedule"} and allocations <= result.keys():
        with localcontext() as context:
            context.prec = 64
            if sum((Decimal(result[field]) for field in allocations), Decimal(0)) != Decimal(result["amount"]):
                raise ValueError("Complete payment allocations must equal amount")
    return result
