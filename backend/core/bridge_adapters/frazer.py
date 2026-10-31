"""Frazer export intake scaffold, not a verified Frazer schema or API integration.

The dealer supplies the actual ID/time columns and all field mappings. No column
names, timestamps, credentials or export-format guarantees are invented here.
"""
from core.bridge_connectors import parse_csv, source_columns_profile


class FrazerExportAdapter:
    version = "frazer-export-profile-v1"
    schema_status = "dealer_supplied_unverified"

    def __init__(self, source_columns=None):
        self.source_columns = source_columns_profile(source_columns)

    def parse(self, content):
        return parse_csv(content, self.source_columns)

    def requirements(self):
        return {"schema_status": self.schema_status, "source_columns": self.source_columns,
                "required_evidence": ["authorized sample export", "stable ID semantics", "source timestamp semantics",
                                      "customer/account relationships", "balance reconciliation"],
                "live_api": False, "writeback": False}
