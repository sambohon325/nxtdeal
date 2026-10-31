"""
Thin API layer for the AI Demo Platform (2026-07-24). All public/unauthenticated — the demo is
a prospect-facing entry that mints its own persona session. Only functional in a DEALEROS_DEMO
tenant (start_demo refuses otherwise, so real dealer backends expose nothing).
"""

from core import demo_mode


def personas_api():
    return demo_mode.get_personas()


def start_demo_api(persona_key, mode="guided", contact=None, access_code=None):
    return demo_mode.start_demo(persona_key, mode=mode, contact=contact, access_code=access_code)


def track_event_api(session_id, kind, detail=None):
    return demo_mode.track_event(session_id, kind, detail=detail)


def get_session_api(session_id):
    return demo_mode.get_session(session_id)


def summarize_session_api(session_id):
    return demo_mode.summarize_session(session_id)
