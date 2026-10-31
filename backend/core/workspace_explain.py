"""
core/workspace_explain.py -- "AI generated content explaining the graph in reference to
whatever prompted it" (session 76). Sam: "it needs a feature where you can add in ai
generated content explaining the graph in refernce to whatever prompted."

Deliberately mirrors core/help_api.py's isolated-OpenAI-call shape (same client/model,
own system prompt, no tool-calling access) rather than reusing core/ai_assistant.py's
ask_ai() -- explaining a chart the user already has on screen needs no graph
tool-calling access at all, the chart's own rows are already the full context, so giving
this path tool access would just be unused surface area on the role-based entity ACL
core/ai_tools.py enforces for the real assistant. Same "don't grant more access than the
job needs" posture help_api.py's own docstring already argues for.
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
    "You are NXTDeal's Workspace assistant. You write a short, plain-English paragraph "
    "(3-5 sentences) explaining a chart or table of real dealership data that the user "
    "just added to their personal Workspace notes. Be specific about what the numbers "
    "show -- name the highest/lowest values, notable gaps, or trends where they exist. "
    "Do not invent numbers not present in the data. If a prompt that led to this chart "
    "is given, tie your explanation back to it. Keep it factual and concise -- this is a "
    "note attached to a chart, not a report."
)


def _describe_rows(rows, label_column, numeric_columns):

    if not rows:
        return "No data rows were provided."

    lines = [f"{len(rows)} rows, columns: {', '.join(numeric_columns)} (labeled by {label_column or 'n/a'})."]

    for row in rows[:25]:
        label = row.get(label_column, "") if label_column else ""
        values = ", ".join(f"{c}={row.get(c)}" for c in numeric_columns if c in row)
        lines.append(f"- {label}: {values}")

    if len(rows) > 25:
        lines.append(f"...and {len(rows) - 25} more rows.")

    return "\n".join(lines)


_DISABLED_ANSWER = (
    "AI chart explanations are currently disabled by your administrator."
)


def explain_chart(
    source_label=None,
    department=None,
    item_key=None,
    label_column=None,
    numeric_columns=None,
    rows=None,
    prompt_context=None,
):
    """No ACL beyond "must be authenticated" -- explaining a chart the caller already
    has the underlying rows for (fetched through the caller's own already-role-filtered
    GET /menu/data call) adds no new data exposure.

    AI Management (Administration Control Center rebuild, continued): checks the real
    'workspace_explain' kill switch (core/ai_management.py,
    ai_workspace_explain_enabled flag), and now wraps the OpenAI call in a try/except
    -- previously this function had no fallback at all on an OpenAI/network failure."""

    if not is_feature_enabled("workspace_explain"):
        record_call_attempt("workspace_explain", "blocked")
        return _DISABLED_ANSWER

    numeric_columns = numeric_columns or []
    rows = rows or []

    context_lines = [
        f"Chart source: {source_label or item_key or 'Untitled'} ({department or 'unknown department'})",
        _describe_rows(rows, label_column, numeric_columns),
    ]

    if prompt_context:
        context_lines.append(f"The user's original question/prompt was: {prompt_context}")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": "\n\n".join(context_lines)
        }
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        record_call_attempt("workspace_explain", "succeeded")
        return response.choices[0].message.content

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network failure falls back rather than raising into the route
        record_call_attempt("workspace_explain", "fell_back", detail=str(exc))
        return f"I'm having trouble reaching the AI service right now ({exc})."
