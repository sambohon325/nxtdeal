import pytest
from core import websites, email_templates
from core.dealeros import ledger
from core.dealer_email_access import email_design_access, validate_email_patch
from core.email_templates_api import update_template_api

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    ledger.reset()
    monkeypatch.setattr(websites, 'save_graph', lambda *_: None)
    monkeypatch.setattr(email_templates, 'save_graph', lambda *_: None)
    yield
    ledger.reset()

def test_only_saved_accessible_website_designs_unlock():
    site=websites.create_website('Synthetic','owner')
    site.attributes['studio_config']={'theme_id':'lone-star'}
    assert email_design_access('SALES','owner')['theme_ids']==['lone-star']
    assert email_design_access('SALES','other')['theme_ids']==[]
    assert email_design_access('MARKETING','marketer')['theme_ids']==['lone-star']
    site.attributes['status']='archived'
    assert email_design_access('MARKETING','marketer')['theme_ids']==[]

def test_locked_design_rejected_without_mutation():
    t=email_templates.create_template('email','Synthetic','owner')
    patch={'blocks':[{'block_key':'html','fields':{'dealer_design':'union','html':'<p>Test</p>'}}]}
    assert 'error' in update_template_api('SALES','owner',t.id,patch)
    assert not t.attributes['blocks']
    site=websites.create_website('Synthetic','owner')
    site.attributes['studio_config']={'theme_id':'union'}
    assert 'error' not in update_template_api('SALES','owner',t.id,patch)
    site.attributes['studio_config']['theme_id']='tempo'
    assert 'error' in update_template_api('SALES','owner',t.id,{'subject':'Changed'})

@pytest.mark.parametrize('html',['<script>alert(1)</script>','<img src="https://example.com/a" onerror="bad()">','<a href="java&#x73;cript:bad()">x</a>','<iframe src="https://example.com"></iframe>','<meta http-equiv="refresh" content="0;url=https://example.com">'])
def test_import_rejects_active_content(html):
    with pytest.raises(ValueError):
        validate_email_patch('SALES','owner',{'blocks':[{'fields':{'email_source':'imported_html','html':html}}]}, {})

def test_own_html_does_not_require_a_website():
    validate_email_patch('SALES','owner',{'blocks':[{'fields':{'email_source':'imported_html','html':'<!doctype html><html><head><meta charset="utf-8"><style>td{color:#333}</style></head><body><table><tr><td><a href="https://example.com">Hello</a></td></tr></table></body></html>'}}]}, {})
