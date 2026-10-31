"""Email brand access follows saved websites in the current tenant ledger."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
from core.websites import list_websites
from core.websites_api import _can_edit_content
from core.permissions import ADMIN, MARKETING


def email_design_access(role, employee_id):
    sites = []
    for site in list_websites():
        if site.attributes.get("status") == "archived":
            continue
        if role not in (ADMIN, MARKETING) and not _can_edit_content(role, employee_id, site):
            continue
        theme = (site.attributes.get("studio_config") or {}).get("theme_id")
        if theme:
            config = site.attributes.get("studio_config") or {}
            identity = config.get("approved_template") or config.get("lone_star") or {}
            sites.append({"id": site.id, "name": site.attributes.get("name", site.id), "theme_id": theme,
                          "dealer_name": identity.get("name") or site.attributes.get("name", ""),
                          "address": next((loc.get("address", "") for loc in identity.get("locations", []) if loc.get("address")), "")})
    return {"theme_ids": sorted({s["theme_id"] for s in sites}), "websites": sites}


class EmailHTMLCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag == "meta" and dict(attrs).get("http-equiv", "").lower() == "refresh":
            raise ValueError("Email HTML cannot redirect the preview.")
        if tag in {"script", "iframe", "object", "embed", "form", "input", "button", "base", "link", "svg", "math", "video", "audio"}:
            raise ValueError("Remove scripts, forms, embedded content and external stylesheets from email HTML.")
        for name, value in attrs:
            if name.startswith("on") or name in {"srcdoc", "formaction"}:
                raise ValueError("Email HTML cannot contain interactive code.")
            if name in {"href", "src", "background", "action", "xlink:href"} and value:
                compact = "".join(value.split())
                scheme = urlsplit(compact).scheme.lower()
                if scheme not in {"https", "mailto", "tel"} and not compact.startswith("#"):
                    raise ValueError("Email links and images must use HTTPS (or mailto/tel links).")

    handle_startendtag = handle_starttag


def validate_email_patch(role, employee_id, patch, existing):
    blocks = patch.get("blocks", existing.get("blocks", []))
    if not isinstance(blocks, list):
        raise ValueError("Email blocks must be a list.")
    allowed = email_design_access(role, employee_id)["theme_ids"]
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("fields", {}), dict):
            raise ValueError("Invalid email block.")
        fields = block.get("fields", {})
        if fields.get("dealer_design") and fields["dealer_design"] not in allowed:
            raise ValueError("Select and save this website design in Website settings to unlock its email templates.")
        if fields.get("email_source") == "imported_html":
            html = fields.get("html", "")
            if not isinstance(html, str) or not html.strip() or len(html.encode("utf-8")) > 500_000:
                raise ValueError("Import an HTML email smaller than 500 KB.")
            if any(s in html.lower() for s in ("javascript:", "vbscript:", "expression(", "@import", "behavior:", "-moz-binding")):
                raise ValueError("Remove active code and imported styles from email HTML.")
            EmailHTMLCheck().feed(html)
