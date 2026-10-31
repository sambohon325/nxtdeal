"""
ACL layer for core/file_manager.py (Bumper parity: File Manager / DAM). Mirrors
media_library_api's posture: every real role can browse the shared asset catalog;
adding/updating/removing a dealership-wide asset is the narrower ADMIN/OPERATIONS/MARKETING
write tier.
"""

from core import file_manager as fm
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC

VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC)
WRITE_ROLES = (ADMIN, OPERATIONS, MARKETING)


def storage_summary_api(role):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the file manager"}
    return fm.storage_summary()


def list_file_categories_api(role):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the file manager"}
    return {"categories": fm.list_categories()}


def list_files_api(role, media_type=None, category=None, query=None):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the file manager"}
    result = fm.list_files(media_type=media_type, category=category, query=query)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"files": result}


def add_file_api(role, employee_id, name, media_type, url, category="general", tags=None,
                 size_bytes=None, content_type=None, description=""):
    if role not in WRITE_ROLES:
        return {"error": "Admin/Operations/Marketing role required to add files"}
    return fm.add_file(
        name, media_type, url, employee_id, category=category, tags=tags,
        size_bytes=size_bytes, content_type=content_type, description=description,
    )


def update_file_api(role, employee_id, file_id, patch):
    if role not in WRITE_ROLES:
        return {"error": "Admin/Operations/Marketing role required to edit files"}
    return fm.update_file(file_id, patch or {})


def remove_file_api(role, employee_id, file_id):
    if role not in WRITE_ROLES:
        return {"error": "Admin/Operations/Marketing role required to remove files"}
    return fm.remove_file(file_id)
