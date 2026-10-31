"""
Persistence for AI-demo leads + accounts (2026-07-25) — a flat {email: record} store at
storage/demo_accounts.json, living in the HUB (not the non-persistent demo tenant) so a
prospect can come back later, and so NXTDeal can work the leads. A record holds the lead
profile (name/position/dealership/city/region/country/phone), the chosen persona, and the
login credential (salt/hash). Atomic write + tolerant load, same as the other Hub stores.
"""

import json
import os

_accounts = {}

DEMO_ACCOUNTS_PATH = "storage/demo_accounts.json"


def get(email):
    return _accounts.get((email or "").strip().lower())


def get_by_username(username):
    u = (username or "").strip().lower()
    if not u:
        return None
    for rec in _accounts.values():
        if (rec.get("username") or "").strip().lower() == u:
            return rec
    return None


def put(email, record):
    _accounts[(email or "").strip().lower()] = record


def all_records():
    return _accounts


def reset():
    _accounts.clear()


def save_demo_accounts(filepath):
    tmp = filepath + ".tmp"
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_accounts, f, indent=4)
    os.replace(tmp, filepath)


def load_demo_accounts(filepath):
    global _accounts
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = {}
    _accounts = data if isinstance(data, dict) else {}
