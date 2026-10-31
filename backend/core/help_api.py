"""
Contextual AI help (2026-07-13, session 34) -- backend for the floating "?" help
widget's "Ask AI" tab (see BUILD_QUEUE.md's "In-App Onboarding + Contextual AI Help"
section). Deliberately separate from core/ai_assistant.py's ask_ai(): this assistant
answers questions about how to USE NXTDeal itself ("what am I looking at", "what can I
do on this screen") rather than questions about dealership data, so it does NOT get
core/ai_tools.py's tool-calling access to the graph -- there's no legitimate reason for
a "how do I use this screen" question to read customer/vehicle/finance records, and
keeping that access out entirely means this endpoint can never become a side-channel
around the role-based entity ACL ai_tools.py otherwise enforces on the main assistant.

Uses the same OpenAI client/model as core/ai_assistant.py (see that module's docstring
for the "staying on OpenAI, not Claude" decision, 2026-07-13 session 12) but with its
own system prompt and no tools -- a single request/response call, no tool-round loop.

Per Sam's ask (session 34): the help assistant should "see what is on screen and give
suggestions." It doesn't literally see pixels -- the frontend (components/HelpWidget.tsx)
builds a small `screen_context` summary from whatever Artifact is currently loaded in the
workspace panel (artifact type, title, and a short human-readable summary of a few key
fields) and sends that alongside the question and the active department tab. This keeps
the same "don't send more graph data to OpenAI than necessary" posture core/ai_tools.py's
docstring already flags for the main assistant -- screen_context is a UI-level summary,
not a raw entity dump.
"""

import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

SYSTEM_PROMPT = (
    "You are NXTDeal's in-app help assistant. You help users understand what they're "
    "looking at right now and what they can do next in NXTDeal -- a graph-native "
    "dealership operating system with a chat-first workspace. Departments: Operations, "
    "Sales, Marketing, Inventory, Service, Finance. Features available: department "
    "dashboards, entity profiles (customers/vehicles/leads/finance contracts), a "
    "marketing asset design/approval workflow, a campaign & customer-lifecycle engine, "
    "a website/inventory builder, and a Deal Desk (multi-scenario desking, in-house "
    "BHPH or outside-lender financing, a structured on-screen contract, and funding). "
    "Nearly everything in NXTDeal is triggered by asking for it in the main chat -- "
    "there are few buttons to click and no manual forms to hunt for, so your answers "
    "should usually suggest an actual phrase the user could type into the chat (e.g. "
    "\"try asking: 'sell a car'\") rather than describing a menu path that doesn't "
    "exist. You are NOT a data assistant -- you don't look up specific customers, "
    "vehicles, or deals; if asked about a specific record, tell the user to ask the "
    "main chat instead. Keep answers short, concrete, and action-oriented. You're told "
    "the user's role, active department tab, and a summary of whatever is currently "
    "open in their workspace panel -- use that to tailor the answer specifically to "
    "what they're looking at; don't ask them to describe their screen, you already "
    "know it."
)


def _describe_screen_context(screen_context):

    if not screen_context:
        return "Nothing is currently open in the workspace panel."

    parts = []

    artifact_type = screen_context.get("artifact_type")
    title = screen_context.get("title")
    summary = screen_context.get("summary")

    if artifact_type:
        parts.append(f"Artifact type currently on screen: {artifact_type}")

    if title:
        parts.append(f"Title: {title}")

    if summary:
        parts.append(f"Summary: {summary}")

    if not parts:
        return "Nothing is currently open in the workspace panel."

    return "\n".join(parts)


_DISABLED_ANSWER = (
    "In-app AI help is currently disabled by your administrator. Try the "
    "Getting Started tab in this same widget, or ask a teammate."
)


def ask_help_api(
    question,
    role=None,
    department=None,
    screen_context=None
):
    """No ACL beyond "must be authenticated" (enforced by api/app.py's _authenticate
    before this is ever called) -- every role can ask for help, same as every role can
    see the "?" button. role/department/screen_context are passed through as plain
    context for the model, not checked against anything.

    AI Management (Administration Control Center rebuild, continued): checks the real
    'help_assistant' kill switch (core/ai_management.py, ai_help_enabled flag) before
    attempting anything, and now wraps the OpenAI call in a try/except -- previously
    this function had no fallback at all on an OpenAI/network failure, unlike every
    other AI feature in this codebase."""

    if not is_feature_enabled("help_assistant"):
        record_call_attempt("help_assistant", "blocked")
        return _DISABLED_ANSWER

    context_lines = [
        f"User's role: {role or 'unknown'}",
        f"Active department tab: {department or 'none'}",
        _describe_screen_context(screen_context)
    ]

    user_content = (
        "\n".join(context_lines) +
        f"\n\nQuestion: {question}"
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_content
        }
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        record_call_attempt("help_assistant", "succeeded")
        return response.choices[0].message.content

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network failure falls back rather than raising into the route
        record_call_attempt("help_assistant", "fell_back", detail=str(exc))
        return (
            f"I'm having trouble reaching the AI service right now ({exc}). Please "
            "try again in a moment."
        )
