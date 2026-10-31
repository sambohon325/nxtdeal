"""Create an isolated, persistent fictional dealership; never copy production data.

Run with the backend Python environment. `create` refuses existing destinations.
`serve` is loopback-only, removes inherited provider settings and disables lifespan
schedulers. This is a rehearsal fixture, not a deployable production seed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKER = "nxtdeal-synthetic-v1"
PASSWORD = "Synthetic-Only-2026!"


def graph():
    entities, relationships = [], []
    def add(identifier, kind, **attributes):
        entities.append(dict(id=identifier, entity_type=kind,
                             attributes={**attributes, "synthetic": True}))
    roles = ["ADMIN", "ADMIN", "SALES", "MARKETING", "SERVICE", "FINANCE", "OPERATIONS"]
    for i, role in enumerate(roles, 1):
        add(f"EMP-{i:05}", "Employee", name=f"Synthetic {role.title()} {i}",
            Name=f"Synthetic {role.title()} {i}", Title=role.title(),
            FirstName="Synthetic", LastName=f"{role.title()} {i}", Department=role.title(),
            role=role, department=role, status="active", email=f"staff{i}@example.test")
    for i in range(1, 13):
        add(f"CUST-{i:05}", "Customer", name=f"Fictional Customer {i}",
            first_name="Fictional", last_name=f"Customer {i}", email=f"customer{i}@example.test",
            FirstName="Fictional", LastName=f"Customer {i}", Email=f"customer{i}@example.test",
            email_consent=False, sms_consent=False)
        add(f"LEAD-{i:05}", "Lead", name=f"Fictional Lead {i}",
            customer_id=f"CUST-{i:05}", status="new", assigned_to="EMP-00003",
            FirstName="Fictional", LastName=f"Lead {i}", Email=f"customer{i}@example.test",
            AssignedSalesperson="EMP-00003", PipelineState="NEW", Source="synthetic-rehearsal",
            email=f"customer{i}@example.test", source="synthetic-rehearsal")
        relationships.append(dict(source_id="EMP-00003", target_id=f"LEAD-{i:05}",
                                  relationship_type="ASSIGNED_TO"))
    for i in range(1, 31):
        add(f"VEH-{i:05}", "Vehicle", year=2024, make="Fictional", model=f"Demo {i}",
            stock_number=f"SYN-{i:04}", status="available", inventory_status="available",
            Year=2024, Make="Fictional", Model=f"Demo {i}", StockNumber=f"SYN-{i:04}",
            Price=20000 + i * 100, Mileage=i * 1000, Condition="Used",
            retail_price=20000 + i * 100, price=20000 + i * 100, mileage=i * 1000,
            condition="used", lifecycle_status="available", disposition="retail")
    for i in range(1, 7):
        add(f"SRV-{i:05}", "ServiceRecord", customer_id=f"CUST-{i:05}",
            vehicle_id=f"VEH-{i:05}", status="open", description="Synthetic inspection",
            ServiceNumber=f"SYN-RO-{i:04}", CustomerID=f"CUST-{i:05}",
            Description="Synthetic inspection", Status="Open", PayType="Customer Pay",
            assigned_to="EMP-00005")
    warranty = warranty_graph()
    return dict(entities=entities + warranty["entities"], relationships=relationships + warranty["relationships"])


def warranty_graph():
    """Additive fictional service records for populated warranty/recall UI rehearsals."""
    entities, relationships = [], []
    def add(identifier, kind, **attributes):
        entities.append(dict(id=identifier, entity_type=kind, attributes={**attributes, "synthetic": True}))
    add("SYN-RECALL-001", "Recall", make="Fictional", model="Recall Demo", open=True,
        recall_number="SYN-RECALL-001", description="Fictional inspection campaign - rehearsal only")
    for i in range(1, 18):
        customer, vehicle, ro = f"SYN-W-CUST-{i:03}", f"SYN-W-VEH-{i:03}", f"SYN-W-RO-{i:03}"
        vin = f"SYNTHETICVIN{i:05}"
        add(customer, "Customer", CustomerID=customer, FirstName="Fictional", LastName=f"Warranty {i}",
            Email=f"warranty{i}@example.test", email_consent=False, sms_consent=False)
        add(vehicle, "Vehicle", VIN=vin, Make="Fictional", Model="Recall Demo", Year=2024,
            Condition="New", Mileage=1000, lifecycle_status="customer_owned")
        add(ro, "ServiceRecord", ServiceNumber=ro, CustomerID=customer, VIN=vin,
            Description="Fictional recall inspection", Status="Open", PayType="Warranty",
            ro_stage="In Progress", Cost=0, PartsCost=0, LaborHours=0, parts_requests=[])
        for source, target, kind in [(customer, vehicle, "OWNS"), (customer, ro, "AUTHORIZED"),
                                     (vehicle, ro, "HAS_SERVICE_RECORD")]:
            relationships.append(dict(source_id=source, target_id=target, relationship_type=kind))
    return dict(entities=entities, relationships=relationships)


def clean_environment(root):
    # Deliberate allowlist: no inherited provider keys, proxies, tenant URLs or secrets.
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL"}}
    marker = json.loads((root / "synthetic.json").read_text())
    if marker.get("kind") != MARKER:
        raise ValueError("Not a synthetic dealership")
    env.update(DEALEROS_STORAGE_DIR=str(root / "dealer"),
               DEALEROS_AUTH_SECRET=marker["auth_secret"], OPENAI_API_KEY="synthetic-no-provider",
               NXTDEAL_MARKETING_DELIVERY_ENABLED="false", NXTDEAL_CLOUD_BACKUPS_ENABLED="false",
               NXTDEAL_MYSALES_ENABLED="true", NXTDEAL_MYSALES_DB=str(root / "hub" / "mysales.sqlite3"),
               NXTDEAL_MYSALES_INVENTORY_ENABLED="false", NXTDEAL_SYNTHETIC="true",
               PYTHONPATH=str(ROOT / "backend"))
    return env


def create(destination):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "dealer").mkdir()
    (root / "hub").mkdir()
    payload = graph()
    for name, value in {"graph.json": payload, "audit.json": [], "credentials.json": {},
                        "customer_credentials.json": {}}.items():
        (root / "dealer" / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    marker = dict(kind=MARKER, auth_secret=secrets.token_hex(32),
                  graph_sha256=hashlib.sha256((root / "dealer/graph.json").read_bytes()).hexdigest(),
                  delivery_enabled=False, provider_evidence="synthetic_only")
    (root / "synthetic.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    os.chmod(root / "synthetic.json", 0o600)
    code = '''from core.auth import credential_store
from core.auth_storage import save_credentials
from core.storage_paths import CREDENTIALS_PATH
roles = ["ADMIN", "ADMIN", "SALES", "MARKETING", "SERVICE", "FINANCE", "OPERATIONS"]
for i, role in enumerate(roles, 1):
    credential_store.set_credential(f"EMP-{i:05}", "Synthetic-Only-2026!", role, must_change_password=False)
save_credentials(CREDENTIALS_PATH)
'''
    subprocess.run([sys.executable, "-c", code], cwd=root, env=clean_environment(root), check=True)
    return {"directory": str(root), "entities": len(payload["entities"]),
            "staff_ids": [f"EMP-{i:05}" for i in range(1, 8)],
            "fixture_password": PASSWORD, "synthetic_only": True}


def serve(root, port, service):
    root = Path(root).resolve()
    env = clean_environment(root)
    if service == "dealer":
        target, app_dir = "synthetic_dealer:app", ROOT / "scripts"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "backend"), str(ROOT / "scripts")])
    else:
        # Minimal Hub surface reuses the actual personal-account and OAuth routers.
        # It never starts provisioning, repair jobs or production Hub schedulers.
        target, app_dir = "synthetic_hub:app", ROOT / "scripts"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "hub"), str(ROOT / "scripts")])
    return subprocess.call([sys.executable, "-m", "uvicorn", target, "--app-dir", str(app_dir),
                            "--host", "127.0.0.1", "--port", str(port), "--lifespan", "off"],
                           cwd=root / service, env=env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "serve"])
    parser.add_argument("directory")
    parser.add_argument("--service", choices=["dealer", "hub"], default="dealer")
    parser.add_argument("--port", type=int, default=8317)
    args = parser.parse_args()
    if args.action == "create":
        print(json.dumps(create(args.directory), indent=2))
    else:
        raise SystemExit(serve(args.directory, args.port, args.service))
