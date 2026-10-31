import json
from pathlib import Path
import pytest
from test_website_studio import site, config
from test_lone_star import lone_star
from core.website_studio import update_studio_api
from core.websites_api import submit_website_api, approve_website_api
from core import websites

from core.website_studio import catalogue
MANIFEST={theme['id']:theme for theme in catalogue()['themes']}

@pytest.mark.parametrize('theme',[x for x in MANIFEST if x!='lone-star'])
def test_approved_design_save_publish_and_owner_isolation(site,theme):
    settings={**lone_star(),'name':MANIFEST[theme]['name']}
    payload=config(theme_id=theme,approved_template=settings)
    assert 'error' in update_studio_api('SALES','other',site.id,payload,0)
    saved=update_studio_api('SALES','owner',site.id,payload,0)
    assert saved['studio_config']['approved_template']==settings
    assert submit_website_api('SALES','owner',site.id)['status']=='pending_approval'
    assert approve_website_api('ADMIN','reviewer',site.id)['status']=='published'
    assert websites.get_website(site.id).attributes['studio_config']['theme_id']==theme
