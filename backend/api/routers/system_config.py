"""System Configuration / Organizations router -- one real singleton
SystemConfig record (core/system_config.py), Administration's "Organizations"
Top Menu item, plus Performance Readiness's real Goal Tracking mechanism
(a flat department -> monthly numeric target stored on the same singleton).

Extracted verbatim out of api/app.py (CAF-00120, god_file_app_py -- splitting
the 14,000+-line monolith into domain-scoped FastAPI routers). Behavior is
unchanged from the original inline routes -- same paths, same request/response
shapes, same auth flow. Static "/system-config/department-goals" registered
before the dynamic "/system-config/department-goals/{department}/clear" path,
matching the original file's own route-shadowing-avoidance ordering.

Viewing open to any authenticated role, editing ADMIN/OPERATIONS-only (see
core/system_config_api.py's own module docstring for the full ACL reasoning).
"""

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr
from core import lobby_information

from api.deps import _authenticate

from core.system_config_api import (
    get_system_config_api,
    update_organization_profile_api,
    add_location_api,
    remove_location_api,
    update_business_hours_api,
    update_defaults_api,
    set_feature_flag_api,
    get_department_goals_api,
    set_department_goal_api,
    clear_department_goal_api,
    get_brand_settings_api,
    update_brand_settings_api,
    list_prompt_templates_api,
    add_prompt_template_api,
    remove_prompt_template_api,
)


router = APIRouter()


class LobbyInformationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: dict[str, StrictStr]
    published: StrictBool


@router.get("/public/lobby")
def public_lobby(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return lobby_information.get_public_lobby()


@router.get("/system-config/lobby")
def lobby_settings(response: Response, authorization: str = Header(None)):
    response.headers["Cache-Control"] = "no-store"
    payload, error = _authenticate(authorization)
    if error:
        response.status_code = 401
        return error
    result = lobby_information.get_lobby_settings(payload["role"])
    if "error" in result:
        response.status_code = 403
    return result


@router.put("/system-config/lobby")
def save_lobby(request: LobbyInformationRequest, response: Response, authorization: str = Header(None)):
    response.headers["Cache-Control"] = "no-store"
    payload, error = _authenticate(authorization)
    if error:
        response.status_code = 401
        return error
    if "error" in lobby_information.get_lobby_settings(payload["role"]):
        response.status_code = 403
        return {"error": "Admin/Operations role required."}
    result = lobby_information.update_lobby_settings(payload["role"], payload["employee_id"],
                                                     request.content, request.published)
    if "error" in result:
        response.status_code = 400
    return result


class UpdateOrgProfileRequest(BaseModel):
    """Body for POST /system-config/organization-profile -- a partial patch,
    same convention as UpdateVendorRequest. See core/system_config.py's
    update_organization_profile()."""

    dealership_name: str = None
    dba_name: str = None
    ein: str = None
    address_line1: str = None
    address_line2: str = None
    city: str = None
    state: str = None
    zip_code: str = None
    phone: str = None
    website_url: str = None


class AddLocationRequest(BaseModel):

    name: str
    address: str
    is_primary: bool = False


class UpdateBusinessHoursRequest(BaseModel):

    day: str
    hours: str


class UpdateDefaultsRequest(BaseModel):

    default_currency: str = None
    default_timezone: str = None


class SetFeatureFlagRequest(BaseModel):

    flag: str
    enabled: bool


class SetDepartmentGoalRequest(BaseModel):
    """Body for POST /system-config/department-goals -- see
    core/system_config.py's set_department_goal(). Performance Readiness's
    real Goal Tracking mechanism (Readiness reframe, item #4)."""

    department: str
    monthly_target: float


class UpdateBrandSettingsRequest(BaseModel):
    """Body for POST /ai-settings/brand -- a partial patch of the dealer's
    brand voice (AI Management dashboard). See core/system_config.py's
    update_brand_settings(). brand_tone must be one of BRAND_TONES; the two
    free-text fields accept any string."""

    brand_tone: str = None
    brand_voice: str = None
    style_guidelines: str = None


class AddPromptTemplateRequest(BaseModel):
    """Body for POST /ai-settings/prompt-templates -- see
    core/system_config.py's add_prompt_template()."""

    name: str
    body: str


@router.get("/system-config")
def system_config_get(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_system_config_api(payload["role"])


@router.post("/system-config/organization-profile")
def system_config_update_profile(request: UpdateOrgProfileRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    fields = {k: v for k, v in request.model_dump().items() if v is not None}

    return update_organization_profile_api(payload["role"], payload["employee_id"], **fields)


@router.post("/system-config/locations")
def system_config_add_location(request: AddLocationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_location_api(
        payload["role"], payload["employee_id"], request.name, request.address, is_primary=request.is_primary
    )


@router.post("/system-config/locations/{index}/remove")
def system_config_remove_location(index: int, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_location_api(payload["role"], payload["employee_id"], index)


@router.post("/system-config/business-hours")
def system_config_update_business_hours(request: UpdateBusinessHoursRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_business_hours_api(payload["role"], payload["employee_id"], request.day, request.hours)


@router.post("/system-config/defaults")
def system_config_update_defaults(request: UpdateDefaultsRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_defaults_api(
        payload["role"],
        payload["employee_id"],
        default_currency=request.default_currency,
        default_timezone=request.default_timezone,
    )


@router.post("/system-config/feature-flags")
def system_config_set_feature_flag(request: SetFeatureFlagRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_feature_flag_api(payload["role"], payload["employee_id"], request.flag, request.enabled)


@router.get("/system-config/department-goals")
def system_config_get_department_goals(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_department_goals_api(payload["role"])


@router.post("/system-config/department-goals")
def system_config_set_department_goal(request: SetDepartmentGoalRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_department_goal_api(
        payload["role"], payload["employee_id"], request.department, request.monthly_target
    )


@router.post("/system-config/department-goals/{department}/clear")
def system_config_clear_department_goal(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return clear_department_goal_api(payload["role"], payload["employee_id"], department)


# ---------------------------------------------------------------------------
# AI Management dashboard -- brand settings + prompt templates (2026-07-23).
# Reads open to any authenticated role, writes ADMIN/OPERATIONS-only (see
# core/system_config_api.py's own ACL reasoning). Static
# "/ai-settings/prompt-templates" registered before the dynamic
# "/ai-settings/prompt-templates/{template_id}" delete path, matching this
# file's own route-shadowing-avoidance ordering.
# ---------------------------------------------------------------------------

@router.get("/ai-settings/brand")
def ai_settings_get_brand(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_brand_settings_api(payload["role"])


@router.post("/ai-settings/brand")
def ai_settings_update_brand(request: UpdateBrandSettingsRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    patch = {k: v for k, v in request.model_dump().items() if v is not None}

    return update_brand_settings_api(payload["role"], payload["employee_id"], patch)


@router.get("/ai-settings/prompt-templates")
def ai_settings_list_prompt_templates(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_prompt_templates_api(payload["role"])


@router.post("/ai-settings/prompt-templates")
def ai_settings_add_prompt_template(request: AddPromptTemplateRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_prompt_template_api(payload["role"], payload["employee_id"], request.name, request.body)


@router.delete("/ai-settings/prompt-templates/{template_id}")
def ai_settings_remove_prompt_template(template_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_prompt_template_api(payload["role"], payload["employee_id"], template_id)
