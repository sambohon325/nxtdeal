from decimal import Decimal
import pytest
from core.entities import Entity
from core.tenant_context import TenantContext
from db.normalized_test_session import NormalizedTestSession
from db.import_preflight import decode_source, InvalidSource


def session(value):
    result = NormalizedTestSession(TenantContext('11111111-1111-1111-1111-111111111111'))
    result.add_entity(Entity('a','Customer',{'value':value}))
    return result


def test_capture_native_numbers_without_losing_exact_loaded_decimals():
    values = [42,0.1,True,Decimal('0.123456789012345678901')]
    graph = session(values)
    captured = graph.capture_snapshot()
    assert decode_source(captured)[0]['entities'][0]['attributes']['value'] == [Decimal(42),Decimal('0.1'),True,values[3]]
    values[0] = 9
    assert graph.capture_snapshot() != captured


@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_capture_rejects_nonfinite_native_numbers(value):
    with pytest.raises(InvalidSource,match='nonfinite_number'):
        session(value).capture_snapshot()


@pytest.mark.parametrize('value', [{1:'integer'}, {True:'boolean'}, {None:'null'},
                                  {'text':1, 2:'mixed'}, {'nested':[{('tuple',):1}]}])
def test_capture_rejects_nonstring_keys_without_coercing_or_mutating(value):
    from copy import deepcopy
    before = deepcopy(value)
    graph = session(value)
    with pytest.raises(InvalidSource, match='^nonstring_object_key$'):
        graph.capture_snapshot()
    assert graph.get_entity('a').attributes['value'] == before


def test_rejected_capture_leaves_prior_bytes_usable_and_can_be_corrected():
    graph = session({'1':'original'})
    before = graph.capture_snapshot()
    graph.get_entity('a').attributes['value'][1] = 'must not merge with string key'
    with pytest.raises(InvalidSource, match='^nonstring_object_key$'):
        graph.capture_snapshot()
    assert decode_source(before)[0]['entities'][0]['attributes']['value'] == {'1':'original'}
    del graph.get_entity('a').attributes['value'][1]
    assert graph.capture_snapshot() == before
