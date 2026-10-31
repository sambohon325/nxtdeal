"""Public marketing artwork bytes; canonical metadata remains shared IMAGE records.

Never serves chat attachments or arbitrary filesystem paths. Uploading here is an
explicit public-marketing action gated by the existing library write roles.
"""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import re
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from core.dealeros import ledger
from core.entity_types import IMAGE
from core.media_library import add_library_image, UPLOADABLE_CATEGORIES
from core.storage_paths import storage_path

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 24_000_000
KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.png$")


def upload_artwork(data, name, category, employee_id):
    if not data or len(data) > MAX_UPLOAD_BYTES:
        return {"error": "Choose an image of 12 MB or less."}
    if category not in UPLOADABLE_CATEGORIES:
        return {"error": "Choose a shared-library category, not inventory."}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP") or getattr(source, "is_animated", False):
                    return {"error": "Use a still JPG, PNG or WebP image."}
                if source.width * source.height > MAX_PIXELS:
                    return {"error": "Choose an image smaller than 24 megapixels."}
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA" if "A" in source.getbands() or "transparency" in source.info else "RGB")
                image.thumbnail((4096, 4096))
                # New raster removes EXIF/GPS, comments and embedded payloads.
                clean = Image.new(image.mode, image.size)
                clean.paste(image)
                output = BytesIO()
                clean.save(output, format="PNG")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        return {"error": "This file is not a supported image. Use JPG, PNG or WebP."}
    key = uuid4().hex + ".png"
    directory = Path(storage_path("public-marketing-images"))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / key
    try:
        with target.open("xb") as handle:
            handle.write(output.getvalue())
        result = add_library_image("/public/media-library/" + key, str(name or "")[:200], category, employee_id, upload_key=key)
        if "error" in result:
            target.unlink(missing_ok=True)
            return result
        return {"image": result}
    except Exception:
        target.unlink(missing_ok=True)
        raise


def public_artwork_path(key):
    if not KEY_PATTERN.fullmatch(key):
        return None
    # An existing canonical library record is required; deletion revokes access.
    if not any(e.entity_type == IMAGE and e.attributes.get("Scope") == "library" and e.attributes.get("PublicUploadKey") == key for e in ledger.get_all().values()):
        return None
    path = Path(storage_path("public-marketing-images")) / key
    return path if path.is_file() else None
