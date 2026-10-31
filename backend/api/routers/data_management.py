"""Data Management router -- Administration Control Center's "Data
Management" Top Menu item: real per-entity-type CSV export
(core/data_backup.py) plus real graph.json backup/restore.

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow.

ADMIN/OPERATIONS for everything except restore, which is ADMIN-only (the
single most consequential real action in this whole codebase -- overwrites
the live graph.json and reloads it in-process). See
core/data_backup_api.py's own module docstring for the full ACL reasoning.
"""

from fastapi import APIRouter, Header
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api.deps import _authenticate

from core.data_backup_api import (
    list_exportable_entity_types_api,
    export_entity_type_csv_api,
    create_backup_api,
    list_backups_api,
    restore_backup_api,
)


router = APIRouter()


class CreateBackupRequest(BaseModel):

    label: str = ""


@router.get("/data-management/exportable-types")
def data_management_exportable_types(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_exportable_entity_types_api(payload["role"])


@router.get("/data-management/export/{entity_type}")
def data_management_export(entity_type: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    filename, content = export_entity_type_csv_api(payload["role"], entity_type)

    if filename is None:
        return content

    return PlainTextResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/data-management/backups")
def data_management_create_backup(request: CreateBackupRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_backup_api(payload["role"], payload["employee_id"], label=request.label)


@router.get("/data-management/backups")
def data_management_list_backups(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_backups_api(payload["role"])


@router.post("/data-management/backups/{backup_id}/restore")
def data_management_restore_backup(backup_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return restore_backup_api(payload["role"], payload["employee_id"], backup_id)
