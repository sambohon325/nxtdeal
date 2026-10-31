import base64
import io
import json
import sqlite3
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import dealer_cloud as cloud


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DEALEROS_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("NXTDEAL_CLOUD_BACKUPS_ENABLED", "true")
    monkeypatch.setenv("NXTDEAL_CLOUD_CONNECTIONS", json.dumps({"drive": {"provider": "google_drive", "remote": "dealer", "root": "DLR-TEST"}}))
    (tmp_path / "graph.json").write_text('{"entities":[],"relationships":[]}')
    (tmp_path / "credentials.json").write_text('{"sensitive":"fixture-only"}')
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    with cloud.db() as con:
        values = cloud.settings(con)
    values.update(backup_connection="drive", photo_connection="drive", public_key=pem)
    cloud.configure(values, "ADMIN-FIXTURE")
    objects = {}
    def transfer(connection, action, name, content=None, **kwargs):
        assert connection == "drive"
        if action == "rcat":
            objects[name] = content
            return b""
        return objects[name]
    monkeypatch.setattr(cloud, "transport", transfer)
    return tmp_path, key, values, objects


def decrypt(blob, key):
    aad, ciphertext = blob.split(b"\n", 1)
    header = json.loads(aad)
    secret = key.decrypt(base64.b64decode(header["wrapped_key"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return AESGCM(secret).decrypt(base64.b64decode(header["nonce"]), ciphertext, aad)


def test_encrypted_cloud_backup_readback_and_offline_recovery(env):
    root,key,_,objects=env
    (root / "backups").mkdir()
    (root / "backups/old.json").write_text("not included")
    result=cloud.run_backup("ADMIN-FIXTURE")
    assert result["state"] == "verified_transfer"
    blob=objects[result["object"]]
    assert b"fixture-only" not in blob
    with zipfile.ZipFile(io.BytesIO(decrypt(blob,key))) as z:
        manifest=json.loads(z.read("manifest.json"))
        assert json.loads(z.read("data/credentials.json"))["sensitive"] == "fixture-only"
        assert "data/backups/old.json" not in z.namelist()
        assert not manifest["external_photo_bytes_included"]
        assert result["restore_verified"] is False
    assert not list(root.glob("*.nxtbackup"))


def test_tampered_ciphertext_is_not_recoverable(env):
    _, key, values, _ = env
    blob=cloud.encrypt_archive(b"data",values["public_key"])
    with pytest.raises(Exception):
        decrypt(blob[:-1]+bytes([blob[-1]^1]),key)


def test_readback_failure_never_claims_verified(env,monkeypatch):
    def transfer(*args,**kwargs): return b"wrong"
    monkeypatch.setattr(cloud,"transport",transfer)
    result=cloud.run_backup()
    assert result["state"] == "failed_or_uncertain"
    assert "verified_at" not in result
    assert cloud.status()["runs"][0]["state"] == "failed_or_uncertain"


def test_transfer_exception_does_not_leak_secrets(env,monkeypatch):
    def transfer(*args,**kwargs): raise RuntimeError("SECRET fixture token")
    monkeypatch.setattr(cloud,"transport",transfer)
    assert "SECRET" not in json.dumps(cloud.run_backup())
    assert "SECRET" not in json.dumps(cloud.status())


def test_disabled_worker_cannot_upload(env,monkeypatch):
    monkeypatch.setenv("NXTDEAL_CLOUD_BACKUPS_ENABLED","false")
    with pytest.raises(cloud.CloudError): cloud.run_backup()
    assert env[3] == {}


def test_schedule_persists_and_due_tick_runs_once(env):
    _,_,values,objects=env
    values["enabled"]=True
    cloud.configure(values,"ADMIN-FIXTURE")
    assert cloud.run_backup(due=True) is None
    with cloud.db() as con:
        value=cloud.settings(con);value["next_run"]=1
        con.execute("UPDATE settings SET body=?",(json.dumps(value),))
    assert cloud.run_backup(due=True)["state"] == "verified_transfer"
    assert cloud.run_backup(due=True) is None
    assert len(objects)==1


def test_cross_worker_lease_blocks_capture_and_settings(env):
    with cloud.db() as con: con.execute("INSERT INTO leases VALUES(1,?)",(cloud.time.time()+600,))
    with pytest.raises(cloud.CloudError): cloud.run_backup()
    with pytest.raises(cloud.CloudError): cloud.configure(env[2],"ADMIN-FIXTURE")


def test_tenant_settings_do_not_follow_other_storage_root(env,tmp_path,monkeypatch):
    other=tmp_path/"other";other.mkdir()
    monkeypatch.setenv("DEALEROS_STORAGE_DIR",str(other))
    assert cloud.status()["settings"]["backup_connection"]==""
    assert cloud.status()["runs"]==[]


def test_unknown_connection_and_private_key_rejected(env):
    values=dict(env[2]);values["backup_connection"]="another-dealer"
    with pytest.raises(cloud.CloudError):cloud.configure(values,"ADMIN-FIXTURE")
    values=dict(env[2]);values["public_key"]=env[1].private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    with pytest.raises(cloud.CloudError):cloud.configure(values,"ADMIN-FIXTURE")


def test_invalid_json_fails_without_transfer(env):
    (env[0]/"graph.json").write_text('{partial')
    assert cloud.run_backup()["state"]=="failed_or_uncertain"
    assert not env[3]


def test_archive_snapshots_sqlite_and_validates_manifest(env):
    path=env[0]/"customer.sqlite"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE test(value)");con.execute("INSERT INTO test VALUES('fixture')")
    payload,_=cloud.archive()
    with zipfile.ZipFile(io.BytesIO(payload)) as z,sqlite3.connect(":memory:") as db:
        db.deserialize(z.read("data/customer.sqlite"))
        assert db.execute("SELECT value FROM test").fetchone()[0]=="fixture"


def test_photo_bytes_go_only_to_remote_and_reference(env,monkeypatch):
    from core.dealeros import ledger
    from core.entities import Entity
    from core import merchandising
    ledger.reset();ledger.add_entity(Entity(id="VEH-CLOUD",entity_type="Vehicle",attributes={}))
    monkeypatch.setattr(merchandising,"save_graph",lambda _:None)
    body=b"\xff\xd8\xff"+b"fixture image"
    result=cloud.upload_photo("VEH-CLOUD",body,"ADMIN-FIXTURE","https://api.example.com")
    photo_id=result["image"]["url"].rsplit("/",1)[1]
    assert cloud.read_photo(photo_id)==(body,"image/jpeg")
    assert not list(env[0].rglob("*.jpg"))
    ledger.entities.pop(result["image"]["id"])
    with pytest.raises(cloud.CloudError):cloud.read_photo(photo_id)


def test_inline_photo_data_rejected(env):
    from core.dealeros import ledger
    from core.entities import Entity
    from core.merchandising import add_vehicle_image
    ledger.reset();ledger.add_entity(Entity(id="VEH-CLOUD",entity_type="Vehicle",attributes={}))
    assert "error" in add_vehicle_image("VEH-CLOUD","data:image/png;base64,xxx","EMP")


def test_http_permissions_and_publication_consent(env,monkeypatch):
    from api.routers import dealer_cloud as routes
    app=FastAPI();app.include_router(routes.router)
    client=TestClient(app)
    monkeypatch.setattr(routes,"_authenticate",lambda _: (None,{"error":"no"}))
    assert client.get("/data-management/cloud").status_code==401
    monkeypatch.setattr(routes,"_authenticate",lambda _: ({"role":"SALES","employee_id":"EMP"},None))
    assert client.get("/data-management/cloud").status_code==403
    monkeypatch.setattr(routes,"_authenticate",lambda _: ({"role":"ADMIN","employee_id":"EMP"},None))
    assert client.get("/data-management/cloud").status_code==200
    assert client.post("/merchandising/vehicles/V/cloud-photo",content=b"abc").status_code==400
    values=dict(env[2]);values.pop("next_run",None);values["interval_hours"]=0
    assert client.put("/data-management/cloud",json=values).status_code==422


def test_transport_uses_scoped_argv_and_no_shell(tmp_path,monkeypatch):
    monkeypatch.setenv("NXTDEAL_CLOUD_CONNECTIONS",json.dumps({"test":{"provider":"dropbox","remote":"tenant","root":"dealer-a"}}))
    config=tmp_path/"rclone.conf";config.write_text("fixture")
    monkeypatch.setenv("NXTDEAL_RCLONE_CONFIG",str(config))
    monkeypatch.setattr(cloud.shutil,"which",lambda _:"rclone")
    seen=[]
    def run(args,**kwargs):
        seen.append((args,kwargs))
        return type("Result",(),{"returncode":0,"stdout":b"ok"})()
    monkeypatch.setattr(cloud.subprocess,"run",run)
    assert cloud.transport("test","cat","photos/a.jpg")==b"ok"
    assert seen[0][0][2]=="tenant:dealer-a/photos/a.jpg"
    assert not seen[0][1].get("shell")
    with pytest.raises(cloud.CloudError):cloud.transport("test","cat","../other/key")
    with pytest.raises(cloud.CloudError):cloud.transport("test","delete","photos/a.jpg")


def test_recovery_cli_restores_only_new_offline_directory(env,tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location("recover_cloud",Path(__file__).resolve().parents[2]/"scripts/recover_dealer_cloud_backup.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=cloud.run_backup()
    backup=tmp_path/"fixture.nxtbackup";backup.write_bytes(env[3][result["object"]])
    keyfile=tmp_path/"private.pem"
    keyfile.write_bytes(env[1].private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    target=tmp_path/"offline"
    recovered=module.recover(backup,keyfile,target)
    assert recovered["format"]==1
    assert json.loads((target/"credentials.json").read_text())["sensitive"]=="fixture-only"
    with pytest.raises(ValueError):module.recover(backup,keyfile,target)
    assert json.loads((env[0]/"graph.json").read_text())["entities"]==[]


def test_changed_files_abort_capture_before_upload(env,monkeypatch):
    original=zipfile.ZipFile.writestr
    def write(z,name,data,*args,**kwargs):
        result=original(z,name,data,*args,**kwargs)
        if name=="data/graph.json": (env[0]/"graph.json").write_text('{"entities":[],"relationships":[],"changed":true}')
        return result
    monkeypatch.setattr(zipfile.ZipFile,"writestr",write)
    assert cloud.run_backup()["state"]=="failed_or_uncertain"
    assert env[3]=={}


def test_malformed_or_oversize_photo_not_transferred(env,monkeypatch):
    from core import merchandising
    monkeypatch.setattr(merchandising,"_get_vehicle",lambda _:True)
    with pytest.raises(cloud.CloudError):cloud.upload_photo("V",b"<svg>script</svg>","EMP","https://example.com")
    monkeypatch.setattr(cloud,"MAX_PHOTO",3)
    with pytest.raises(cloud.CloudError):cloud.upload_photo("V",b"\xff\xd8\xffxxxx","EMP","https://example.com")
    assert env[3]=={}


def test_expired_lease_marks_interrupted_run_and_allows_new_run(env):
    with cloud.db() as con:
        con.execute("INSERT INTO leases VALUES(1,1)")
        con.execute("INSERT INTO runs VALUES('old',1,'running','{}')")
    assert cloud.run_backup()["state"]=="verified_transfer"
    assert next(r for r in cloud.status()["runs"] if r["id"]=="old")["state"]=="interrupted"
