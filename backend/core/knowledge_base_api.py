"""
Thin API-layer functions for the role-gated knowledge base (2026-07-13, session 38),
imported directly into api/app.py's route handlers -- same "no service layer
indirection" convention every other `*_api.py` module in this codebase follows.

No blanket ACL tuple here (unlike compliance/network/employee value) -- every
authenticated role can list/read articles; core/knowledge_base.py's `_visible_to()`
does the actual per-article filtering against each article's own `visible_roles`,
matching the "general read access, narrower per-item gate" split ASSET/CAMPAIGN/
WEBSITE already draw between read access and approve access.
"""

from core.knowledge_base import list_articles, get_article


def _serialize(article):
    return {"id": article.id, **article.attributes}


def list_articles_api(role, department=None, category=None):

    return {"articles": [_serialize(a) for a in list_articles(role, department, category)]}


def get_article_api(role, article_id):

    article = get_article(article_id, role)

    if not article:
        return {"error": "Article not found or not visible to your role"}

    return _serialize(article)
