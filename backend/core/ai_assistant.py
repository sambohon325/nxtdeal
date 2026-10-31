"""
Phase 11 — AI assistant. Calls the real OpenAI API (gpt-4o-mini) — confirmed NOT
rules-based, see CLAUDE.md's 2026-07-13 correction. Sam decided (2026-07-13) to stay on
OpenAI for now rather than migrate to Claude; if that changes later, swap the OpenAI
client below for an Anthropic one — core/ai_api.py's ask() only depends on ask_ai()'s
(question, role) -> str signature, not on anything OpenAI-specific.

Phase 11 wrap-up (2026-07-13): added tool-calling access to core/ai_tools.py's
graph-traversal functions, so the assistant can look up real entities instead of only
answering from the question text or the workload/leaderboard/escalation fast paths in
core/ai_api.py. See core/ai_tools.py's docstring for the role-based access control this
respects, and the data-flow note about entity data now being sent to OpenAI once a tool
is used.

Session 76 (Sam: "when its clearly leading to showing in dashboard format, lets lead
them to their [dashboard]... can you pull up the info for John Smith - it should say
would you like to look at his lead status? (click here)"): ask_ai() now also returns
which real entities it actually resolved via tool calls during the round-trip, so
core/ai_api.py's ask() can offer real "jump to the right department dashboard"
suggestions (core/entity_menu_links.py) instead of leaving the user with just a text
answer. This doesn't change what the model sees or how it answers -- it's a pure
side-channel collection of tool results already flowing through this function.

Session 76 follow-up (Sam: "can you say build me a report, have it pull the numbers and
make a editable graph in workspace... if i wanted to create various reports from
different departments or areas via chat, i could"): ask_ai() now ALSO returns a
report_suggestion whenever the model calls core/ai_tools.py's propose_report tool
(list_report_sources -> get_department_data -> propose_report is the intended chain --
see each tool's docstring) -- a validated {department, item_key, source_label,
field_path, label_column, numeric_columns, chart_type} config core/ai_api.py forwards
as `suggested_report`, which the frontend renders as a "Build Report in Workspace"
button that drops a live chart + an AI-written note onto the user's Workspace board.
Same side-channel pattern as resolved_entities -- doesn't change what the model sees.
"""

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_tools import TOOLS, call_tool
from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

# Bounds the tool-call back-and-forth so a confused model can't loop forever burning
# API calls. Bumped 4 -> 7 (session 76 second follow-up, after a live trace showed the
# model burning its whole budget calling get_department_data across several
# departments for a vague "put what you can in the workspace" follow-up and running out
# of rounds before ever reaching propose_report) -- enough room for
# list_report_sources + 2-3 get_department_data calls + propose_report + one retry on a
# validation error, without letting a genuinely confused model loop forever.
MAX_TOOL_ROUNDS = 7

SYSTEM_PROMPT = (
    "You are NXTDeal AI, an assistant over a car dealership's graph-native operating "
    "system. Use the available tools to look up real customers, vehicles, leads, "
    "finance contracts, and service records before answering questions about specific "
    "records — don't guess or invent entity IDs or details. If a tool returns a "
    "'Forbidden' or 'not found' error, tell the user plainly rather than making "
    "something up.\n\n"
    "If the user asks you to build/pull/chart a report, or asks to see numbers/a graph "
    "for some area of the dealership (e.g. 'build me a report on service revenue', "
    "'can I see a chart of sales pipeline', or a vaguer follow-up like 'just put what "
    "you can in the workspace'), your job is NOT done until you have actually called "
    "propose_report at least once — a prose summary alone does not satisfy this kind of "
    "request, no matter how detailed, because it never reaches the user's Workspace. "
    "Follow this chain: call list_report_sources once to see every real department + "
    "item you can report on, call get_department_data on ONE closest-matching item to "
    "inspect its real fields, then immediately call propose_report with a "
    "field_path/label_column/numeric_columns you actually saw in that response — never "
    "invent field names. Do not call get_department_data on more than 2-3 items before "
    "committing to a propose_report call with your best available option; exploring "
    "every department at length instead of picking one and finishing is a failure mode, "
    "not thoroughness. If propose_report returns an error, read it (it lists the real "
    "available fields) and retry immediately with corrected arguments rather than "
    "moving on to a different data source. If the user's request is genuinely too vague "
    "to pick one specific metric, ask a brief clarifying question instead of dumping a "
    "multi-department prose summary. After a successful propose_report call, tell the "
    "user in plain language what the report shows — that explanation becomes the note "
    "attached to the chart in their Workspace, so write it as a short, direct "
    "explanation of the chart, not a bulleted recap of the whole conversation.\n\n"
    "Operations and Sales both run on real, trackable v2 workflow instances — "
    "Operations' pilot catalog (Vehicle Intake, Recon, Deal Jacket Audit, Title "
    "Exception, Interdepartment SLA, New Employee Onboarding, and similar) and "
    "Sales' own 18-workflow lifecycle catalog across Prospecting/Engagement/Deals/"
    "Finance/Retention (Lead Management, BDC Workflow, Up System, Appointment "
    "Workflow, Showroom Workflow, Demo Drive, Trade Appraisal, Desking, Credit "
    "Application, Manager TO, F&I Handoff, F&I Workflow, eSignature, Delivery "
    "Experience, Equity Mining, Lease Maturity, Lost Sale Recovery, Orphan Owner "
    "Mining, and similar) — each instance has a current step, a next step, and can "
    "be blocked, waiting on an approval, or escalated. If the user asks about a "
    "specific workflow instance (they'll usually give or imply an instance id like "
    "'WF2-00042', or ask something like 'what's blocking the recon on that truck' "
    "or 'where's this deal's credit app at'), call get_workflow_instance_status "
    "with that instance_id and answer using its real current_step/next_step/blocked "
    "steps/pending approvals/suggested_actions — never guess at what step something is "
    "on. If they ask a broader question first ('what Sales workflows are open on "
    "this deal', 'find the recon instance for VEH-00231'), call "
    "list_workflow_instances (filtered by linked entity, department, workflow_key, or "
    "status) to find the right instance_id before drilling into one. If they ask "
    "something dealership-wide — how many workflows are in progress, what's blocked "
    "right now, what's escalated, in Operations, Sales, or both — call "
    "get_workflow_dashboard for the real definition-by-definition counts instead of "
    "guessing at a total. If they ask what's falling behind, overdue, or needs "
    "attention in either department without naming a specific workflow, call "
    "get_stalled_workflow_instances and proactively name the real stalled "
    "instances with their reason, rather than waiting to be asked about each one "
    "individually — surfacing a real blocker unprompted is the correct, expected "
    "behavior here, not overstepping. These four tools are read-only: you can see and "
    "explain a workflow instance's real state, but you cannot advance, block, approve, "
    "or escalate one through chat — tell the user to use the workflow's own Step "
    "Progression screen for that."
)


def _collect_resolved_entities(tool_result, seen_ids, resolved_entities):
    """Pulls real {id, entity_type, attributes} records out of a tool_result, whatever
    shape it came in as -- get_entity_by_id returns a single entity dict,
    search_entities returns a list of entity dicts, get_related_entities returns a list
    of {relationship_type, entity} dicts. De-dupes by id and caps how many are kept
    (a chatty tool round could otherwise surface 20 search hits) -- the cap here is
    generous since core/entity_menu_links.py applies the real, tighter
    MAX_SUGGESTED_ACTIONS cap on the suggestion list itself."""

    def _maybe_add(candidate):
        if (
            isinstance(candidate, dict)
            and isinstance(candidate.get("id"), str)
            and isinstance(candidate.get("entity_type"), str)
            and candidate["id"] not in seen_ids
        ):
            seen_ids.add(candidate["id"])
            resolved_entities.append(candidate)

    if isinstance(tool_result, dict):
        _maybe_add(tool_result)
        return

    if isinstance(tool_result, list):
        for item in tool_result[:20]:
            if isinstance(item, dict) and "entity" in item:
                _maybe_add(item.get("entity"))
            else:
                _maybe_add(item)


_DISABLED_ANSWER = (
    "The AI Assistant is currently disabled by your administrator. Please use the "
    "dashboards directly, or check back once it's re-enabled."
)

_UNREACHABLE_ANSWER_PREFIX = (
    "I'm having trouble reaching the AI service right now"
)


def ask_ai(
    question,
    role=None,
    employee_id=None
):
    """Returns (answer_text, resolved_entities, report_suggestion). resolved_entities is
    a list of the real {id, entity_type, attributes} records this call actually looked
    up via tool calls (empty if the model never called a tool, e.g. a general knowledge
    question). report_suggestion is the validated dict from the last successful
    propose_report tool call this turn, or None if the model never built one.

    AI Management (Administration Control Center rebuild, continued): checks the real
    'ai_assistant' kill switch (core/ai_management.py, backed by
    core/system_config.py's ai_assistant_enabled flag) before attempting anything, and
    now wraps the whole OpenAI round-trip in a try/except -- previously this was the
    one real AI feature in this codebase with NO fallback on an OpenAI/network
    failure, unlike every other AI-backed function here, which would have raised an
    unhandled exception into the chat route instead of degrading gracefully.

    `employee_id` (security-hardening pass, 2026-07-20, Task #5): optional,
    threaded through from api/app.py's /ai/chat route via core/ai_api.py's
    ask() -- recorded as the real `actor` on every AiActionLog entry this
    call produces. This is the one feature in AI_FEATURE_CATALOG with real
    tool-calling graph access, so it's the first (and, as of this pass, only)
    call site with a real actor threaded all the way through -- see
    core/ai_audit.py's own module docstring for the honest scope note on
    every other AI feature still recording actor=None."""

    if not is_feature_enabled("ai_assistant"):
        record_call_attempt("ai_assistant", "blocked", actor=employee_id, prompt_summary=question)
        return _DISABLED_ANSWER, [], None

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": question
        }
    ]

    seen_ids = set()
    resolved_entities = []
    report_suggestion = None

    try:
        for _ in range(MAX_TOOL_ROUNDS):

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS
            )

            message = response.choices[0].message

            if not message.tool_calls:

                record_call_attempt(
                    "ai_assistant", "succeeded",
                    actor=employee_id, prompt_summary=question, output_summary=message.content,
                )
                return message.content, resolved_entities, report_suggestion

            messages.append(message)

            for tool_call in message.tool_calls:

                try:
                    arguments = json.loads(
                        tool_call.function.arguments
                    )
                except (ValueError, TypeError):
                    arguments = {}

                result = call_tool(
                    tool_call.function.name,
                    role,
                    arguments
                )

                _collect_resolved_entities(result, seen_ids, resolved_entities)

                if (
                    tool_call.function.name == "propose_report"
                    and isinstance(result, dict)
                    and result.get("ok")
                ):
                    report_suggestion = result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str)
                })

        # Ran out of tool-call rounds — ask once more without tools to force a plain
        # answer instead of looping indefinitely.
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        record_call_attempt(
            "ai_assistant", "succeeded",
            actor=employee_id, prompt_summary=question,
            output_summary=response.choices[0].message.content,
        )
        return (
            response
            .choices[0]
            .message
            .content,
            resolved_entities,
            report_suggestion
        )

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network failure falls back rather than raising into the chat route, matching every other AI feature in this codebase
        record_call_attempt(
            "ai_assistant", "fell_back", detail=str(exc),
            actor=employee_id, prompt_summary=question,
        )
        return (
            f"{_UNREACHABLE_ANSWER_PREFIX} ({exc}). Please try again in a moment, or "
            "use the dashboards directly.",
            resolved_entities,
            report_suggestion,
        )
