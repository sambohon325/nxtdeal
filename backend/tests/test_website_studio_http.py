"""Actual ASGI/auth/review/contact routes against an isolated synthetic tenant.

conftest.py redirects all storage to a disposable directory. Lifespan is
intentionally not entered, so background workers and providers never start.
"""
import os
import sys
from pathlib import Path
from copy import deepcopy
from uuid import uuid4
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_authenticated_studio_review_and_public_inquiry():
    # conftest establishes isolation before core imports and checks it again.
    isolated = Path(os.environ["DEALEROS_STORAGE_DIR"]).resolve()
    assert isolated.name.startswith("dealeros_pytest_storage_")
    from api.app import app
    from fastapi.testclient import TestClient
    from core.auth import credential_store
    from core.dealeros import ledger
    from core.entities import Entity
    from core.storage_paths import GRAPH_PATH
    # A previous import must never silently redirect this test to a real tenant.
    assert Path(str(GRAPH_PATH)).resolve().is_relative_to(isolated)
    previous = deepcopy(credential_store.credentials)
    ledger.reset()
    client = TestClient(app)
    try:
        headers = {}
        for actor, role in [("SYN-STUDIO-OWNER", "SALES"), ("SYN-STUDIO-OTHER", "SALES"), ("SYN-STUDIO-REVIEWER", "ADMIN")]:
            credential_store.set_credential(actor, "Synthetic-only-password2026!", role, must_change_password=False)
            response = client.post("/auth/login", json={"employee_id": actor, "password": "Synthetic-only-password2026!"})
            assert response.status_code == 200, response.text
            headers[actor] = {"Authorization": "Bearer " + response.json()["token"]}
        owner, other, reviewer = headers.values()
        from io import BytesIO
        from PIL import Image
        image_bytes = BytesIO()
        Image.new("RGB", (32, 24), "navy").save(image_bytes, "PNG")
        files = {"file": ("synthetic.png", image_bytes.getvalue(), "image/png")}
        assert "error" in client.post("/media-library/upload", files=files).json()
        assert "error" in client.post("/media-library/upload", headers=owner, files=files).json()
        uploaded = client.post("/media-library/upload", headers=reviewer, files=files, data={"category": "general", "name": "Synthetic art"}).json()
        assert "image" in uploaded, uploaded
        artwork = uploaded["image"]["url"]
        image_response = client.get(artwork)
        assert image_response.status_code == 200
        assert image_response.headers["content-type"] == "image/png"
        assert image_response.headers["x-content-type-options"] == "nosniff"
        assert "error" in client.post("/media-library/upload", headers=reviewer, files={"file": ("bad.png", b"<svg/>", "image/png")}).json()

        assert "error" in client.get("/website-studio/catalogue").json()
        catalogue = client.get("/website-studio/catalogue", headers=owner).json()
        assert "themes" in catalogue, catalogue
        assert len(catalogue["themes"]) == 20
        body = {"name": "Synthetic HTTP Dealer", "theme_id": "tempo", "request_id": str(uuid4())}
        created = client.post("/website-studio/sites", headers=owner, json=body).json()
        assert created["status"] == "draft", created
        site_id = created["id"]
        path = "/websites/" + site_id
        assert client.post("/website-studio/sites", headers=owner, json=body).json()["id"] == site_id
        assert "error" in client.get(path, headers=other).json()
        assert "error" in client.get("/public/websites/" + site_id).json()
        settings = {"config": {"version": 1, "theme_id": "tempo", "language": "es", "backgrounds": {"about": artwork}, "social_links": {"instagram": "https://example.test/synthetic"}}, "expected_revision": 1}
        assert "error" in client.put(path + "/studio", headers=other, json=settings).json()
        saved = client.put(path + "/studio", headers=owner, json=settings).json()
        assert saved["studio_revision"] == 2, saved
        assert "error" in client.put(path + "/studio", headers=owner, json=settings).json()
        submitted = client.post(path + "/submit", headers=owner).json()
        assert submitted["status"] == "pending_approval", submitted
        assert "error" in client.post(path + "/pages/home/sections/0/edit", headers=owner, json={"fields": {"headline": "Unreviewed"}}).json()
        assert "error" in client.post(path + "/approve", headers=owner, json={}).json()
        approved = client.post(path + "/approve", headers=reviewer, json={}).json()
        assert approved["status"] == "published", approved
        public = client.get("/public/websites/" + site_id).json()
        assert public["studio_config"]["language"] == "es"
        assert public["studio_config"]["backgrounds"]["about"] == artwork
        assert "owners" not in public and "published_snapshot" not in public
        ledger.add_entity(Entity(id="SYN-HTTP-VEHICLE", entity_type="Vehicle", attributes={"Make": "Synthetic", "VIN": "SYNTHETIC-HTTP"}))
        stock = client.get("/public/websites/" + site_id + "/inventory", params={"q": "synthetic"}).json()
        assert stock["total"] == 1 and stock["vehicles"][0]["id"] == "SYN-HTTP-VEHICLE"
        assert client.get("/public/websites/" + site_id + "/inventory", params={"page_size": 100}).status_code == 422
        assert "error" in client.get("/public/websites/missing/inventory").json()
        sections = public["pages"]["contact"]["sections"]
        index = next(i for i, section in enumerate(sections) if section["section_key"] == "contact_form")
        inquiry = {"page_key": "contact", "section_index": index, "name": "Synthetic Shopper", "email": "test@example.test", "vehicle_id": "SYN-HTTP-VEHICLE", "intent": "purchase", "request_id": str(uuid4())}
        contact_path = "/public/websites/" + site_id + "/contact"
        first = client.post(contact_path, json=inquiry).json()
        assert "lead_id" in first, first
        assert client.post(contact_path, json=inquiry).json() == first
        assert sum(e.entity_type == "Lead" for e in ledger.get_all().values()) == 1
        lead = ledger.get_entity(first["lead_id"])
        assert lead.attributes["WebsiteVehicleID"] == "SYN-HTTP-VEHICLE"
        assert lead.attributes["AssignedSalesperson"] == "SYN-STUDIO-OWNER"
        inquiry["name"] = "Changed shopper"
        assert "error" in client.post(contact_path, json=inquiry).json()
        assert "error" in client.post(path + "/studio/draft", headers=other).json()
        draft = client.post(path + "/studio/draft", headers=owner).json()
        assert draft["status"] == "draft"
        edited_settings = {"config": {"version": 1, "theme_id": "union", "language": "en"}, "expected_revision": draft["studio_revision"]}
        assert "error" not in client.put(path + "/studio", headers=owner, json=edited_settings).json()
        assert client.get("/public/websites/" + site_id).json()["studio_config"]["theme_id"] == "tempo"
        assert client.get("/public/websites/" + site_id + "/vehicles/SYN-HTTP-VEHICLE").json()["theme_id"] == "tempo"
        assert client.get("/public/websites/" + site_id + "/sitemap.xml").status_code == 200
        assert client.post(path + "/submit", headers=owner).json()["status"] == "pending_approval"
        assert client.post(path + "/reject", headers=reviewer, json={"notes": "Synthetic revision"}).json()["status"] == "rejected"
        assert client.get("/public/websites/" + site_id).json()["studio_config"]["theme_id"] == "tempo"
        assert client.post(path + "/submit", headers=owner).json()["status"] == "pending_approval"
        assert client.post(path + "/approve", headers=reviewer, json={}).json()["status"] == "published"
        assert client.get("/public/websites/" + site_id).json()["studio_config"]["theme_id"] == "union"
        # The persisted graph contains first-write provenance and the retry key.
        persisted = Path(str(GRAPH_PATH)).read_text(encoding="utf-8")
        assert inquiry["request_id"] in persisted and "WebsiteVehicleID" in persisted
    finally:
        client.close()
        ledger.reset()
        credential_store.load_credentials(previous)
