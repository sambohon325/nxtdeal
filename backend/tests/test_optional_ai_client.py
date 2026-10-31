from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from core import optional_ai_client


def test_construction_is_deferred_and_shared_across_concurrent_use(monkeypatch):
    chat = object()
    factory = Mock(return_value=SimpleNamespace(chat=chat))
    monkeypatch.setattr(optional_ai_client, 'OpenAI', factory)
    client = optional_ai_client.LazyOpenAI(api_key='fictional-test-key')
    factory.assert_not_called()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(value is chat for value in pool.map(lambda _: client.chat, range(30)))
    factory.assert_called_once_with(api_key='fictional-test-key')


def test_constructor_failure_is_not_cached_or_replaced_with_dummy_credentials(monkeypatch):
    factory = Mock(side_effect=ValueError('not configured'))
    monkeypatch.setattr(optional_ai_client, 'OpenAI', factory)
    client = optional_ai_client.LazyOpenAI(api_key=None)
    for _ in range(2):
        with pytest.raises(ValueError, match='not configured'):
            _ = client.chat
    assert factory.call_count == 2
    assert factory.call_args.kwargs == {'api_key': None}


def test_disabled_assistant_never_constructs_provider(monkeypatch):
    from core import ai_assistant
    factory = Mock(side_effect=AssertionError('must not construct provider'))
    monkeypatch.setattr(optional_ai_client, 'OpenAI', factory)
    monkeypatch.setattr(ai_assistant, 'client', optional_ai_client.LazyOpenAI(api_key=None))
    monkeypatch.setattr(ai_assistant, 'is_feature_enabled', lambda _: False)
    monkeypatch.setattr(ai_assistant, 'record_call_attempt', Mock())
    answer, entities, report = ai_assistant.ask_ai('Fictional question')
    assert answer == ai_assistant._DISABLED_ANSWER
    assert entities == [] and report is None
    factory.assert_not_called()


def test_unconfigured_assistant_uses_existing_fallback(monkeypatch):
    from core import ai_assistant
    monkeypatch.setattr(optional_ai_client, 'OpenAI', Mock(side_effect=ValueError('not configured')))
    monkeypatch.setattr(ai_assistant, 'client', optional_ai_client.LazyOpenAI(api_key=None))
    monkeypatch.setattr(ai_assistant, 'is_feature_enabled', lambda _: True)
    recorded = Mock()
    monkeypatch.setattr(ai_assistant, 'record_call_attempt', recorded)
    answer, entities, report = ai_assistant.ask_ai('Fictional question')
    assert answer.startswith(ai_assistant._UNREACHABLE_ANSWER_PREFIX)
    assert entities == [] and report is None
    assert recorded.call_args.args[:2] == ('ai_assistant', 'fell_back')
