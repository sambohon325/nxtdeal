"""Bridge and native modules share prefixes; concurrent IDs must stay unique."""
from concurrent.futures import ThreadPoolExecutor
from time import sleep
import pytest

from core.id_generator import IDGenerator


class YieldingCounters(dict):
    def __getitem__(self, key):
        value = super().__getitem__(key)
        sleep(0)  # Force a scheduling opportunity between counter read and write.
        return value


def test_concurrent_bridge_and_native_id_allocation_cannot_overwrite_each_other():
    generator = IDGenerator()
    generator.counters = YieldingCounters(generator.counters)
    with ThreadPoolExecutor(max_workers=12) as workers:
        ids = list(workers.map(lambda _: generator.generate("CUST"), range(300)))
    assert len(set(ids)) == 300
    assert {int(value.split("-")[1]) for value in ids} == set(range(1, 301))
    assert generator.generate("BRG") == "BRG-00001"


def test_recovery_is_monotonic_and_ignores_unknown_prefixes():
    generator = IDGenerator()
    generator.reserve_at_least("BRG", 150)
    generator.reserve_at_least("BRG", 20)
    assert generator.generate("BRG") == "BRG-00151"
    generator.reserve_at_least("NOT-A-PREFIX", 999)
    assert "NOT-A-PREFIX" not in generator.counters
    with pytest.raises(KeyError): generator.generate("NOT-A-PREFIX")


def test_recovery_and_allocation_share_one_monotonic_boundary():
    generator = IDGenerator()
    generator.counters = YieldingCounters(generator.counters)
    def allocate(number):
        if number % 3 == 0:
            generator.reserve_at_least("VEH", number * 10)
        return generator.generate("VEH")
    with ThreadPoolExecutor(max_workers=8) as workers:
        ids = list(workers.map(allocate, range(120)))
    assert len(set(ids)) == 120
    assert generator.counters["VEH"] >= 1170


@pytest.mark.parametrize("value", [True, -1, 1.2, "1", None])
def test_recovery_position_is_strict(value):
    with pytest.raises(ValueError): IDGenerator().reserve_at_least("BRG", value)
