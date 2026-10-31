"""Decrypt and validate a dealer backup into a NEW OFFLINE directory.

Never replaces live storage or starts NXTDeal. Private keys are read from a file,
never accepted as a command-line value. Requires cryptography from backend requirements.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_BYTES = 128 * 1024 * 1024


def recover(backup, private_key, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Destination must not exist. Recover into a new offline directory.")
    if Path(backup).stat().st_size > MAX_BYTES + 1024 * 1024:
        raise ValueError("Archive exceeds supported size.")
    blob = Path(backup).read_bytes()
    aad, ciphertext = blob.split(b"\n", 1)
    header = json.loads(aad)
    if header.get("format") != "nxtdeal-backup-v1":
        raise ValueError("Unsupported backup format.")
    key = serialization.load_pem_private_key(Path(private_key).read_bytes(), password=None)
    secret = key.decrypt(base64.b64decode(header["wrapped_key"], validate=True),
                         padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    plain = AESGCM(secret).decrypt(base64.b64decode(header["nonce"], validate=True), ciphertext, aad)
    # Validate all entries before writing anything. Never zip.extractall untrusted names.
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        entries = archive.infolist()
        if len(entries) > 10001 or sum(x.file_size for x in entries) > MAX_BYTES + 2*1024*1024:
            raise ValueError("Archive expansion exceeds supported limits.")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive paths.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != 1:
            raise ValueError("Unsupported manifest.")
        files = manifest["files"]
        if len(files) != len({r["path"] for r in files}):
            raise ValueError("Duplicate manifest paths.")
        if set(names) != {"manifest.json"} | {"data/" + row["path"] for row in files}:
            raise ValueError("Archive and manifest differ.")
        checked = []
        for row in files:
            path = PurePosixPath(row["path"])
            if path.is_absolute() or not path.parts or any(p in {".", ".."} or ":" in p or "\\" in p for p in path.parts):
                raise ValueError("Unsafe archive path.")
            content = archive.read("data/" + row["path"])
            if len(content) != row["bytes"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ValueError("File checksum mismatch.")
            checked.append((path, content))
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        for path, content in checked:
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as out:
                os.chmod(target, 0o600)
                out.write(content)
        return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup")
    parser.add_argument("private_key_file")
    parser.add_argument("new_offline_directory")
    args = parser.parse_args()
    try:
        result = recover(args.backup, args.private_key_file, args.new_offline_directory)
        print(f"Validated and recovered {len(result['files'])} files offline. No live database was changed.")
        print("Application consistency and a real restore drill remain separate checks.")
    except Exception:
        raise SystemExit("Recovery failed. Check key, archive integrity, and a new empty destination. No live restore was attempted.")
