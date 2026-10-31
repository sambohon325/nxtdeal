"""
Tests for the role-gated knowledge base (core/knowledge_base.py,
core/knowledge_base_api.py) -- session 38. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entity_types import KNOWLEDGE_ARTICLE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING

from core import knowledge_base
from core import knowledge_base_api


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


def test_seed_articles_creates_every_seed_entry():

    knowledge_base.seed_articles()

    articles = [e for e in ledger.get_all().values() if e.entity_type == KNOWLEDGE_ARTICLE]

    assert len(articles) == len(knowledge_base.SEED_ARTICLES)


def test_seed_articles_is_idempotent():

    knowledge_base.seed_articles()
    first_count = len(ledger.get_all())

    knowledge_base.seed_articles()
    second_count = len(ledger.get_all())

    assert first_count == second_count


def test_list_articles_open_article_visible_to_any_role():

    knowledge_base.seed_articles()

    for role in (SALES, MARKETING, OPERATIONS, ADMIN):

        articles = knowledge_base.list_articles(role)
        keys = [a.attributes["key"] for a in articles]

        assert "how_to_build_a_deal" in keys


def test_list_articles_restricted_article_hidden_from_non_admin_ops():

    knowledge_base.seed_articles()

    articles = knowledge_base.list_articles(SALES)
    keys = [a.attributes["key"] for a in articles]

    assert "how_to_review_compliance" not in keys
    assert "how_to_use_admin_roster_audit" not in keys


def test_list_articles_restricted_article_visible_to_operations():

    knowledge_base.seed_articles()

    articles = knowledge_base.list_articles(OPERATIONS)
    keys = [a.attributes["key"] for a in articles]

    assert "how_to_review_compliance" in keys


def test_list_articles_admin_only_article_hidden_from_operations():

    knowledge_base.seed_articles()

    articles = knowledge_base.list_articles(OPERATIONS)
    keys = [a.attributes["key"] for a in articles]

    assert "how_to_use_admin_roster_audit" not in keys


def test_list_articles_admin_sees_everything():

    knowledge_base.seed_articles()

    articles = knowledge_base.list_articles(ADMIN)

    assert len(articles) == len(knowledge_base.SEED_ARTICLES)


def test_list_articles_filters_by_department():

    knowledge_base.seed_articles()

    articles = knowledge_base.list_articles(ADMIN, department="sales")

    assert all(a.attributes.get("department") in ("sales", "all") for a in articles)
    assert any(a.attributes["key"] == "getting_started_sales" for a in articles)


def test_get_article_returns_none_for_restricted_role():

    knowledge_base.seed_articles()

    article = knowledge_base.get_article("KB-how_to_review_compliance", SALES)

    assert article is None


def test_get_article_returns_article_for_allowed_role():

    knowledge_base.seed_articles()

    article = knowledge_base.get_article("KB-how_to_review_compliance", ADMIN)

    assert article is not None
    assert article.attributes["title"] == "How To: Review Compliance Alerts"


# ---------------------------------------------------------------------------
# knowledge_base_api.py
# ---------------------------------------------------------------------------

def test_list_articles_api_shape():

    knowledge_base.seed_articles()

    result = knowledge_base_api.list_articles_api(SALES)

    assert "articles" in result
    assert all("id" in a and "title" in a for a in result["articles"])


def test_get_article_api_not_found_message_for_restricted_role():

    knowledge_base.seed_articles()

    result = knowledge_base_api.get_article_api(SALES, "KB-how_to_review_compliance")

    assert "error" in result


def test_get_article_api_found_for_admin():

    knowledge_base.seed_articles()

    result = knowledge_base_api.get_article_api(ADMIN, "KB-how_to_review_compliance")

    assert "title" in result
