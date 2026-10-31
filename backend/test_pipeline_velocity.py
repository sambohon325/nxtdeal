from core.workflow_storage import (
    load_workflows
)

from core.pipeline_velocity import (
    get_pipeline_velocity
)

load_workflows(
    "storage/workflows.json"
)

print(
    get_pipeline_velocity()
)