"""
core/notification_preferences_api.py -- thin API layer over
core/notification_preferences.py, imported directly into api/app.py's GET/POST
/notification-preferences route handlers. No extra ACL beyond "must be
authenticated" (already enforced by api/app.py's _authenticate) -- notification
preferences are purely personal, per-employee data.
"""

from core.notification_preferences import get_preferences, save_preferences


def get_notification_preferences_api(employee_id):
    return get_preferences(employee_id)


def save_notification_preferences_api(employee_id, preferences):
    return save_preferences(employee_id, preferences)
