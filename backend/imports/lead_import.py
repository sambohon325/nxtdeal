import csv

from core.entities import Entity
from core.dealeros import (
    ledger,
    registry,
    id_generator
)

from core.entity_types import LEAD

from core.relationships import Relationship
from core.relationship_types import INTERESTED_IN, ASSIGNED_TO


# Maps the CRM-style "Status" values generate_seed_data.py writes into leads.csv onto
# the pipeline state machine's state names (core/workflows.py's LEAD_WORKFLOW) — see
# CLAUDE.md's "one graph" note (2026-07-13). A real dealership's lead source data uses
# looser status labels than the strict workflow states NXTDeal enforces once a lead is
# actively being worked, hence the mapping instead of a 1:1 match.
STATUS_TO_PIPELINE_STATE = {
    "New": "NEW",
    "Contacted": "CONTACTED",
    "Qualified": "APPOINTMENT_SET",
    "Nurturing": "VISITED",
    "Lost": "LOST",
}


def import_leads(csv_path):

    imported = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            lead_id = id_generator.generate(
                "LEAD"
            )

            lead = Entity(
                id=lead_id,
                entity_type=LEAD,
                attributes=dict(row)
            )

            ledger.add_entity(lead)

            registry.register_lead(
                row["LeadID"],
                lead_id
            )

            vin = row["VIN"]

            vehicle = registry.find_vehicle(vin)

            if vehicle:

                ledger.add_relationship(
                    Relationship(
                        source_id=lead_id,
                        target_id=vehicle,
                        relationship_type=INTERESTED_IN
                    )
                )

            # Seed pipeline state + salesperson assignment straight onto the graph
            # (core/pipeline_state.py + the ASSIGNED_TO relationship type) so the
            # workload/leaderboard/pipeline/escalation/followup dashboards have real data
            # to show once these leads are loaded — see CLAUDE.md's "one graph" note.
            # Written directly at the ledger level (not via core.lead_workflows /
            # core.lead_assignment's higher-level helpers) so a 100-row import doesn't
            # trigger 100 individual audit events + disk saves; run_seed_import.py does
            # one save_graph() at the end for all of it.
            status = row.get("Status")

            if status:

                state = STATUS_TO_PIPELINE_STATE.get(status, "NEW")

                created_at = row.get("CreatedDate") or None

                lead.attributes["PipelineState"] = state

                if created_at:
                    lead.attributes["PipelineCreatedAt"] = created_at
                    lead.attributes["PipelineStateSince"] = created_at

            salesperson_key = row.get("AssignedSalesperson")

            if salesperson_key:

                employee_id = registry.find_employee(
                    salesperson_key
                )

                if employee_id:

                    ledger.add_relationship(
                        Relationship(
                            source_id=employee_id,
                            target_id=lead_id,
                            relationship_type=ASSIGNED_TO
                        )
                    )

            imported += 1

    return imported