"""
Bumper-parity Bulk Import (2026-07-25): CSV parse, column mapping, dedupe (against the
existing graph AND within the batch), non-destructive preview, and commit. Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD
from core import bulk_import
from core import bulk_import_api


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


CSV = (
    "First Name,Last Name,Email,Phone,City\r\n"
    "Jane,Doe,jane@doe.com,555-111-2222,Austin\r\n"
    "John,Smith,john@smith.com,(555) 333 4444,Dallas\r\n"
    "Bad,Row,,,Nowhere\r\n"                      # no email/phone -> error
    "Jane,Dupe,JANE@DOE.COM,999,Houston\r\n"     # dup of row 1 by email (case-insensitive)
)

MAPPING = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Email": "email",
    "Phone": "phone",
    "City": "city",
}


def test_parse_csv_reads_headers_and_rows():
    headers, rows = bulk_import.parse_csv(CSV)
    assert headers == ["First Name", "Last Name", "Email", "Phone", "City"]
    assert len(rows) == 4
    assert rows[0]["First Name"] == "Jane"


def test_suggest_mapping_matches_common_headers():
    m = bulk_import.suggest_mapping(["First Name", "LASTNAME", "e-mail", "Mobile", "Junk"], "lead")
    assert m["First Name"] == "first_name"
    assert m["LASTNAME"] == "last_name"
    assert m["e-mail"] == "email"
    assert m["Mobile"] == "phone"
    assert "Junk" not in m


def test_preview_is_nondestructive_and_classifies_rows():
    before = len(ledger.get_all())
    _, rows = bulk_import.parse_csv(CSV)
    plan = bulk_import.plan_import(rows, MAPPING, "lead")
    assert plan["total"] == 4
    assert plan["will_create"] == 2          # Jane, John
    assert plan["duplicates"] == 1           # Jane dupe (within-batch, by email)
    assert plan["errors"] == 1               # Bad Row, no contact handle
    assert len(ledger.get_all()) == before   # nothing written


def test_commit_creates_leads_and_skips_dupes():
    _, rows = bulk_import.parse_csv(CSV)
    result = bulk_import.run_import(rows, MAPPING, "lead", "EMP-1")
    assert result["created_count"] == 2
    assert result["skipped_count"] == 1
    assert result["error_count"] == 1
    leads = [e for e in ledger.get_all().values() if e.entity_type == LEAD]
    assert len(leads) == 2
    emails = {e.attributes["Email"].lower() for e in leads}
    assert emails == {"jane@doe.com", "john@smith.com"}
    # Imported lead carries the canonical shape + ASSIGNED_TO wiring (created via
    # lead_intake.create_lead), so it's indistinguishable from a hand-entered one.
    jane = next(e for e in leads if e.attributes["Email"] == "jane@doe.com")
    assert jane.attributes["AssignedSalesperson"] == "EMP-1"
    assert jane.attributes["PipelineState"] == "NEW"


def test_dedupe_against_existing_graph():
    # An existing customer with the same email should suppress the imported row.
    ledger.add_entity(Entity(id="CUST-9", entity_type=CUSTOMER, attributes={"Email": "jane@doe.com"}))
    _, rows = bulk_import.parse_csv(CSV)
    result = bulk_import.run_import(rows, MAPPING, "lead", "EMP-1")
    assert result["created_count"] == 1      # only John; Jane matches existing CUST-9
    assert any(s["duplicate_of"]["match"] == "CUST-9" for s in result["skipped"])


def test_dedupe_can_be_disabled():
    ledger.add_entity(Entity(id="CUST-9", entity_type=CUSTOMER, attributes={"Email": "jane@doe.com"}))
    _, rows = bulk_import.parse_csv(CSV)
    result = bulk_import.run_import(rows, MAPPING, "lead", "EMP-1", dedupe=False)
    # dedupe off: both Jane rows + John create; only the no-contact row still errors
    assert result["created_count"] == 3
    assert result["error_count"] == 1


def test_customer_target_creates_customers():
    _, rows = bulk_import.parse_csv(CSV)
    result = bulk_import.run_import(rows, MAPPING, "customer", "EMP-1")
    assert result["created_count"] == 2
    custs = [e for e in ledger.get_all().values() if e.entity_type == CUSTOMER]
    assert len(custs) == 2
    assert all("CustomerID" in c.attributes for c in custs)


# --- API layer ---

def test_api_commit_requires_marketing_or_admin():
    from core.permissions import ADMIN, SALES
    blocked = bulk_import_api.commit_import_api(SALES, "EMP-1", CSV, MAPPING, "lead")
    assert "error" in blocked
    assert len([e for e in ledger.get_all().values() if e.entity_type == LEAD]) == 0
    ok = bulk_import_api.commit_import_api(ADMIN, "EMP-1", CSV, MAPPING, "lead")
    assert ok["created_count"] == 2


def test_api_analyze_suggests_mapping_without_writing():
    from core.permissions import SALES
    before = len(ledger.get_all())
    out = bulk_import_api.analyze_csv_api(CSV, "lead")
    assert out["row_count"] == 4
    assert out["suggested_mapping"]["Email"] == "email"
    assert len(out["sample_rows"]) == 4
    assert len(ledger.get_all()) == before


def test_api_preview_open_to_any_role_but_writes_nothing():
    before = len(ledger.get_all())
    plan = bulk_import_api.preview_import_api(CSV, MAPPING, "lead")
    assert plan["will_create"] == 2
    assert len(ledger.get_all()) == before


def test_row_ceiling_enforced():
    rows = [{"First Name": f"A{i}", "Last Name": "B", "Email": f"a{i}@x.com"} for i in range(bulk_import.MAX_IMPORT_ROWS + 1)]
    out = bulk_import.plan_import(rows, {"First Name": "first_name", "Last Name": "last_name", "Email": "email"}, "lead")
    assert "error" in out
