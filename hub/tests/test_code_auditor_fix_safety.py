"""Unsafe persistence repairs must remain review-only; never touch a repository."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from hub_core.code_auditor import _generate_save_graph_fix

IMPORTS = 'from core.storage import save_graph\nfrom core.storage_paths import GRAPH_PATH\n'


def test_straight_line_mutation_gets_one_save_before_result():
    source = IMPORTS + 'def update(entity):\n    entity.attributes["name"] = "new"\n    return True\n'
    fixed = _generate_save_graph_fix(source)
    assert fixed is not None
    # Execute the generated function against inert fakes to verify ordering.
    events = []
    namespace = {'save_graph': lambda path: events.append(path), 'GRAPH_PATH': 'test-graph'}
    exec(fixed[len(IMPORTS):], namespace)
    class Entity:
        attributes = {}
    assert namespace['update'](Entity()) is True
    assert events == ['test-graph']


@pytest.mark.parametrize('source', [
    'from core import system_config\ndef update(entity):\n    entity.attributes["name"] = "new"\n    system_config.save_graph(system_config.GRAPH_PATH)\n',
    '# save_graph GRAPH_PATH\ndef update(entity):\n    entity.attributes["name"] = "new"\n',
    IMPORTS.replace('import save_graph', 'import save_graph as persist') + 'def update(entity):\n    entity.attributes["name"] = "new"\n',
    IMPORTS + 'def update(entity, allowed):\n    if not allowed:\n        return False\n    entity.attributes["name"] = "new"\n    return True\n',
    IMPORTS + 'def update(entity):\n    try:\n        entity.attributes["name"] = "new"\n    except Exception:\n        return False\n',
])
def test_uncertain_binding_or_control_flow_is_not_auto_fixed(source):
    assert _generate_save_graph_fix(source) is None
