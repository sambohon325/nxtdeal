import csv
import io
from copy import deepcopy
import pytest
from core.spreadsheet_export import spreadsheet_cell
from core.entities import Entity
from core.entity_types import CUSTOMER
from core.dealeros import ledger
from core import data_backup, audit_center


@pytest.mark.parametrize("value", ['=1+1', '+SUM(A1)', '-1+2', '@SUM(A1)', '\tvalue', '\rvalue', '\nvalue',
                                   '  =1', '\ufeff=1', '\x00=1', '＝1', '＋1', '－1', '＠A1'])
def test_untrusted_formula_like_text_has_visible_marker(value):
    assert spreadsheet_cell(value) == '[text] ' + value


@pytest.mark.parametrize("value", [None, '', 'Normal text', 'a=b', 42, -12.5, True, '[text] =1'])
def test_normal_text_and_numeric_values_remain_unchanged(value):
    assert spreadsheet_cell(value) == value


def test_entity_export_protects_dynamic_headers_ids_and_values_without_changing_source():
    ledger.reset()
    entity = Entity('=ID()', CUSTOMER, {'=HEADER()': '=VALUE()', 'Note': 'ordinary,quoted"\n=not-a-new-cell', 'Balance': -12.5})
    ledger.add_entity(entity)
    original = deepcopy(entity)
    try:
        _, content = data_backup.export_entity_type_csv(CUSTOMER)
        rows = list(csv.reader(io.StringIO(content)))
        assert rows[0] == ['id', '[text] =HEADER()', 'Note', 'Balance']
        assert rows[1] == ['[text] =ID()', '[text] =VALUE()', entity.attributes['Note'], '-12.5']
        assert entity == original
    finally:
        ledger.reset()


def test_audit_export_protects_untrusted_actor_and_summary_without_mutation(monkeypatch):
    events = [{'id': 'AUD-1', 'actor': '=ACTOR()', 'summary': '  +FORMULA()', 'details': {'original': '=keep'}}]
    original = deepcopy(events)
    monkeypatch.setattr(audit_center, 'search_audit_log', lambda **kwargs: {'events': events})
    _, content = audit_center.export_audit_events_csv()
    row = next(csv.DictReader(io.StringIO(content)))
    assert row['actor'] == '[text] =ACTOR()'
    assert row['summary'] == '[text]   +FORMULA()'
    assert events == original
