"""Lossless UTC creation-prefix index; other timestamp formats remain candidates."""

# Only the fixed-width microsecond UTC form is safe for lexical comparison.
# Pydantic emits Z; datetime.isoformat emits +00:00. Offset, second-only and
# legacy forms use the empty prefix so they always reach the exact Python check.
STAMP = "json_extract(payload,'$.created_at')"
PATTERN = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]"
CREATION = (
    f"CASE WHEN substr({STAMP},1,26) GLOB '{PATTERN}' "
    f"AND (substr({STAMP},27)='Z' OR substr({STAMP},27)='+00:00') "
    f"THEN substr({STAMP},1,26) ELSE '' END"
)
KINDS_SQL = "kind IN ('deliberation','reallocation','shadow_review','decision_cycle')"
INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS runs_analysis_creation ON runs("
    "json_extract(payload,'$.entity')," + CREATION + ") WHERE " + KINDS_SQL + ";\n"
)
