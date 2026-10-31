"""Synthetic artwork bytes only; no network or customer records."""
from io import BytesIO
from pathlib import Path
import sys
import pytest
from PIL import Image, PngImagePlugin
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import media_library, media_uploads
from core.dealeros import ledger

@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ledger.reset()
    monkeypatch.setenv("DEALEROS_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(media_library, "save_graph", lambda *_: None)
    yield
    ledger.reset()

def png():
    buffer = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Private metadata", "GPS-not-for-public")
    Image.new("RGB", (48, 32), "navy").save(buffer, "PNG", pnginfo=metadata)
    return buffer.getvalue()

def test_sanitized_upload_uses_existing_library_and_revocable_public_route():
    result = media_uploads.upload_artwork(png(), "Synthetic artwork", "general", "owner")
    image = result["image"]
    key = image["url"].rsplit("/", 1)[1]
    path = media_uploads.public_artwork_path(key)
    assert path and path.is_file()
    with Image.open(path) as decoded:
        assert decoded.size == (48, 32)
        assert "Private metadata" not in decoded.info
    assert b"GPS-not-for-public" not in path.read_bytes()
    assert media_library.list_library_images()[0]["id"] == image["id"]
    media_library.remove_library_image(image["id"])
    assert media_uploads.public_artwork_path(key) is None

@pytest.mark.parametrize("data", [b"<svg onload='alert(1)'/>", b"not-an-image", b"", b"x" * (media_uploads.MAX_UPLOAD_BYTES + 1)], ids=["svg", "invalid", "empty", "oversized"])
def test_rejects_non_raster_or_oversized_payload_without_record(data):
    assert "error" in media_uploads.upload_artwork(data, "bad", "general", "owner")
    assert not ledger.get_all()

def test_persistence_failure_leaves_no_record_or_bytes(monkeypatch, tmp_path):
    def fail(*_): raise OSError("Synthetic write failure")
    monkeypatch.setattr(media_library, "save_graph", fail)
    with pytest.raises(OSError): media_uploads.upload_artwork(png(), "Test", "logos", "owner")
    assert not ledger.get_all()
    assert not list(tmp_path.rglob("*.png"))

def test_rejects_traversal_missing_records_and_inventory_category():
    for key in ["../graph.json", "a" * 32 + ".svg", "a" * 32 + ".png"]:
        assert media_uploads.public_artwork_path(key) is None
    assert "error" in media_uploads.upload_artwork(png(), "Test", "inventory", "owner")
    assert not ledger.get_all()
