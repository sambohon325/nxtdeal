"""Approved email suggestions from canonical, available website inventory."""
from html import escape
from urllib.parse import urlsplit
from fastapi import HTTPException
from core.dealeros import ledger
from core.websites import get_live_inventory


def available():
    rows = get_live_inventory(limit=len(ledger.get_all()) + 1)
    return [{k: row.get(k) for k in ("id", "year", "make", "model", "trim", "price", "image_url", "stock", "location_name")} for row in rows if str(ledger.get_entity(row["id"]).attributes.get("Status", "")).lower() not in {"sold", "wholesale", "unavailable", "deleted"}]


def snapshot(ids):
    rows = {r["id"]: r for r in available()}
    if len(set(ids)) != len(ids) or any(i not in rows for i in ids):
        raise HTTPException(409, "A suggested vehicle is no longer available. Update the campaign inventory before sending")
    return [rows[i] for i in ids]


def render(rows):
    html, text = [], []
    for row in rows:
        title = " ".join(str(row[k]) for k in ("year", "make", "model", "trim") if row.get(k))
        details = " · ".join(str(v) for v in (row.get("price") and f'Price: {row["price"]}', row.get("stock") and f'Stock: {row["stock"]}', row.get("location_name")) if v)
        photo = str(row.get("image_url") or "")
        p = urlsplit(photo)
        image = f'<img src="{escape(photo, quote=True)}" alt="{escape(title, quote=True)}" width="560" style="width:100%;height:auto;display:block;border-radius:8px">' if p.scheme == "https" and p.hostname and not p.username else ""
        html.append(f'<div style="padding:16px 0">{image}<h3>{escape(title)}</h3><p>{escape(details)}</p></div>')
        text.append(title + "\n" + details)
    return ('<div style="max-width:600px;margin:auto;padding:24px;font:16px/1.5 Arial"><h2>Suggested vehicles / Vehículos sugeridos</h2>' + "".join(html) + '</div>', "\n\nSuggested vehicles / Vehículos sugeridos\n" + "\n\n".join(text))
