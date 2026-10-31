"""
Thin API layer for AI-demo lead capture + accounts (2026-07-25). Validate + call + shape,
matching the Hub's *_api.py convention. Sign-up/login/reset are public; listing leads is admin.
"""

from hub_core import demo_leads


def signup_api(**kwargs):
    return demo_leads.sign_up(**kwargs)


def login_api(identifier, password):
    return demo_leads.log_in(identifier, password)


def request_reset_api(email):
    return demo_leads.request_reset(email)


def reset_password_api(email, token, new_password):
    return demo_leads.reset_password(email, token, new_password)


def list_leads_api():
    return {"leads": demo_leads.list_leads()}


def config_api():
    return demo_leads.config()
