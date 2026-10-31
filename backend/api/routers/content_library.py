"""
Content Library router (Bumper parity, 2026-07-25): the Campaign-Template Library
(core/campaign_template_library.py) and the File Manager / DAM (core/file_manager.py).

Static /campaign-templates/* and /files/* collection paths registered before their dynamic
/{id} paths to avoid route shadowing. Browsing is open to any authed role; template
authoring is MARKETING/ADMIN; DAM writes are ADMIN/OPERATIONS/MARKETING.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.campaign_template_library_api import (
    list_template_categories_api,
    list_templates_api,
    get_template_api,
    create_template_api,
    delete_template_api,
    instantiate_template_api,
)
from core.file_manager_api import (
    storage_summary_api,
    list_file_categories_api,
    list_files_api,
    add_file_api,
    update_file_api,
    remove_file_api,
)


router = APIRouter()


# ---- Campaign-Template Library ----

class CreateCampaignTemplateRequest(BaseModel):

    name: str
    campaign_type: str
    channel: str
    default_params: dict = {}
    category: str = "General"
    description: str = ""
    suggested_subject: str = ""
    suggested_body: str = ""
    tags: list = []


class InstantiateTemplateRequest(BaseModel):

    name_override: str | None = None
    params_override: dict | None = None
    channel_override: str | None = None


@router.get("/campaign-templates/categories")
def campaign_template_categories_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_template_categories_api(payload["role"])


@router.get("/campaign-templates")
def list_campaign_templates_route(category: str = None, campaign_type: str = None, query: str = None,
                                  authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_templates_api(payload["role"], category=category, campaign_type=campaign_type, query=query)


@router.post("/campaign-templates")
def create_campaign_template_route(request: CreateCampaignTemplateRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_template_api(
        payload["role"], payload["employee_id"], request.name, request.campaign_type, request.channel,
        default_params=request.default_params, category=request.category, description=request.description,
        suggested_subject=request.suggested_subject, suggested_body=request.suggested_body, tags=request.tags,
    )


@router.get("/campaign-templates/{template_id}")
def get_campaign_template_route(template_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_template_api(payload["role"], template_id)


@router.post("/campaign-templates/{template_id}/instantiate")
def instantiate_campaign_template_route(template_id: str, request: InstantiateTemplateRequest,
                                        authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return instantiate_template_api(
        payload["role"], payload["employee_id"], template_id,
        name_override=request.name_override, params_override=request.params_override,
        channel_override=request.channel_override,
    )


@router.delete("/campaign-templates/{template_id}")
def delete_campaign_template_route(template_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_template_api(payload["role"], payload["employee_id"], template_id)


# ---- File Manager / DAM ----

class AddFileRequest(BaseModel):

    name: str
    media_type: str
    url: str
    category: str = "general"
    tags: list = []
    size_bytes: int | None = None
    content_type: str | None = None
    description: str = ""


class UpdateFileRequest(BaseModel):

    patch: dict = {}


@router.get("/files/summary")
def files_summary_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return storage_summary_api(payload["role"])


@router.get("/files/categories")
def files_categories_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_file_categories_api(payload["role"])


@router.get("/files")
def list_files_route(media_type: str = None, category: str = None, query: str = None,
                     authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_files_api(payload["role"], media_type=media_type, category=category, query=query)


@router.post("/files")
def add_file_route(request: AddFileRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_file_api(
        payload["role"], payload["employee_id"], request.name, request.media_type, request.url,
        category=request.category, tags=request.tags, size_bytes=request.size_bytes,
        content_type=request.content_type, description=request.description,
    )


@router.post("/files/{file_id}/update")
def update_file_route(file_id: str, request: UpdateFileRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_file_api(payload["role"], payload["employee_id"], file_id, request.patch)


@router.delete("/files/{file_id}")
def delete_file_route(file_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_file_api(payload["role"], payload["employee_id"], file_id)
