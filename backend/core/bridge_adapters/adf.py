"""Bounded ADF structure discovery, not a lead importer or conformance claim.

ADF requestdate is creation time. No modified_at, source ID selection, consent,
contact selection or vehicle selection is invented by this inspection adapter.
"""
from hashlib import sha256
from xml.parsers import expat
from core.bridge_contracts import source_timestamp, SourceTimePrecisionError


class Node:
    def __init__(self, tag, attributes):
        self.tag, self.attributes, self.children, self.text = tag, attributes, [], []

    def named(self, name):
        return [child for child in self.children if child.tag == name]

    def value(self):
        return "".join(self.text).strip()


def _tree(content):
    if not isinstance(content, str):
        raise ValueError("UTF-8 ADF XML text required")
    try:
        raw = content.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("ADF must contain valid UTF-8 text") from None
    if not raw or len(raw) > 1_000_000:
        raise ValueError("ADF upload must be between 1 byte and 1 MB")
    parser = expat.ParserCreate(namespace_separator="}")
    stack, roots = [], []
    count = 0

    def reject(*args):
        raise ValueError("DTD and entity declarations are not supported in ADF uploads")

    def start(tag, attrs):
        nonlocal count
        count += 1
        if count > 20000 or len(stack) >= 32:
            raise ValueError("ADF exceeds supported XML depth or element count")
        if len(tag) > 120 or "}" in tag or len(attrs) > 20 or any(len(k) > 120 or len(v) > 500 for k, v in attrs.items()):
            raise ValueError("ADF requires bounded unqualified XML elements and attributes")
        node = Node(tag, attrs)
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)

    def declaration(version, encoding, standalone):
        if encoding and encoding.lower().replace("-", "") != "utf8":
            raise ValueError("ADF XML declaration must use UTF-8")

    parser.XmlDeclHandler = declaration
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda tag: stack.pop()
    parser.CharacterDataHandler = lambda value: stack[-1].text.append(value) if stack else None
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    try:
        parser.Parse(raw, True)
    except expat.ExpatError:
        raise ValueError("Malformed ADF XML") from None
    if len(roots) != 1 or roots[0].tag != "adf":
        raise ValueError("ADF upload requires an adf root element")
    root = roots[0]
    if any(child.tag != "prospect" for child in root.children):
        raise ValueError("ADF root may contain only prospect elements")
    if not 1 <= len(root.children) <= 1000:
        raise ValueError("ADF upload requires 1 to 1000 prospects")
    return raw, root


def inspect(content):
    """Return data-minimal review evidence; never store or return lead values."""
    raw, root = _tree(content)
    rows = []
    for index, prospect in enumerate(root.children, 1):
        issues = []
        ids = prospect.named("id")
        if not ids or any(not item.value() or item.children for item in ids):
            issues.append("stable_source_id_required")
        if len(ids) > 1:
            issues.append("source_id_selection_required")
        dates = prospect.named("requestdate")
        if len(dates) != 1 or dates[0].children:
            issues.append("single_creation_time_required")
        else:
            try:
                source_timestamp(dates[0].value())
            except SourceTimePrecisionError:
                issues.append("source_time_precision_requires_adapter")
            except ValueError:
                issues.append("timezone_aware_creation_time_required")
        customers = prospect.named("customer")
        contacts = [contact for customer in customers for contact in customer.named("contact")]
        if len(customers) != 1 or len(contacts) != 1:
            issues.append("customer_contact_selection_required")
        for contact in contacts:
            if len(contact.named("email")) > 1 or len(contact.named("phone")) > 1:
                issues.append("contact_value_selection_required")
                break
        vehicles = prospect.named("vehicle")
        if len(vehicles) > 1:
            issues.append("vehicle_selection_required")
        rows.append({"row_number": index, "source_id_count": len(ids), "customer_contact_count": len(contacts),
                     "vehicle_count": len(vehicles), "issues": issues})
    return {"adapter_version": "adf-discovery-v1", "file_format": "adf", "source_bytes": len(raw),
            "content_hash": sha256(raw).hexdigest(), "row_count": len(rows), "rows": rows,
            "stored": False, "status": "review_required", "import_available": False,
            "timestamp_semantics": {"requestdate": "lead_created_at", "modified_at": "not_provided"},
            "notice": "Structure inspection only, not full ADF validation. No lead values are retained or returned. Review provider ID scope, repeated contacts and vehicles, and creation-event semantics before implementing an approved import profile. Request date is never substituted for modified time. This does not authorize contact, create consent, receive email or activate an import."}


def creation_events(content, *, id_source):
    """Extract a strict selected-field draft, with no persistence or approval.

    The provider's exact id/@source is caller-supplied, never guessed. Multiple
    contacts or selected values are rejected, even if the text happens to match.
    Vehicle, vendor, comments, finance and consent are outside this profile.
    """
    from core.bridge_contracts import SourceEvent
    if not isinstance(id_source, str) or not id_source.strip() or id_source != id_source.strip() or len(id_source) > 120:
        raise ValueError("Exact bounded provider ID source required")
    _, root = _tree(content)
    events = []

    def one(nodes, label, required=False):
        if len(nodes) > 1 or required and not nodes:
            raise ValueError(f"ADF draft requires one {label}")
        if not nodes:
            return ""
        if nodes[0].children:
            raise ValueError(f"ADF draft requires plain text {label}")
        value = nodes[0].value()
        if required and not value:
            raise ValueError(f"ADF draft requires one {label}")
        return value

    for prospect in root.children:
        external_id = one([node for node in prospect.named("id") if node.attributes.get("source") == id_source], "selected provider ID", True)
        created_at = one(prospect.named("requestdate"), "creation time", True)
        customers = prospect.named("customer")
        if len(customers) != 1 or len(customers[0].named("contact")) != 1:
            raise ValueError("ADF draft requires one customer contact")
        contact = customers[0].named("contact")[0]
        names = contact.named("name")
        values = {}
        for part in ("first", "last", "full"):
            value = one([node for node in names if node.attributes.get("part") == part], f"{part} name")
            if value:
                values[f"name_{part}"] = value
        for field in ("email", "phone"):
            value = one(contact.named(field), field)
            if value:
                values[field] = value
        if not values:
            raise ValueError("ADF draft has no supported customer identity fields")
        # Do not split full names, interpret email/phone consent, or turn a
        # resend flag into a new modification timestamp.
        events.append(SourceEvent("adf_prospects", external_id, created_at, id_source, "created", values))
    return tuple(events)
