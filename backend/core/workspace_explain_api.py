"""
core/workspace_explain_api.py -- thin wrapper over core/workspace_explain.py for
api/app.py's POST /workspace-board/explain route handler.
"""

from core.workspace_explain import explain_chart


def explain_chart_api(
    source_label=None,
    department=None,
    item_key=None,
    label_column=None,
    numeric_columns=None,
    rows=None,
    prompt_context=None,
):
    text = explain_chart(
        source_label=source_label,
        department=department,
        item_key=item_key,
        label_column=label_column,
        numeric_columns=numeric_columns,
        rows=rows,
        prompt_context=prompt_context,
    )

    return {"text": text}
