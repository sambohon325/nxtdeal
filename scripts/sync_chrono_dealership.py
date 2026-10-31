"""Refresh the immutable shared Chrono bundle from a reviewed local commit.
Usage: python scripts/sync_chrono_dealership.py CHRONO_CHECKOUT COMMIT
Commit the resulting manifest and source together; never edit bundled files.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess
p=argparse.ArgumentParser()
p.add_argument('checkout'); p.add_argument('commit')
a=p.parse_args()
target=Path(__file__).resolve().parents[1]/'backend/chrono/shared'
manifest=json.loads((target/'MANIFEST.json').read_text())
commit=subprocess.check_output(['git','-C',a.checkout,'rev-parse',a.commit+'^{commit}'],text=True).strip()
for name in dict.fromkeys([*manifest['files'], 'dealership/planner.py', 'dealership/peers.py', 'dealership/peer_data.json', 'dealership/PEER_SOURCE.json', 'dealership/register.py', 'dealership/REGISTER_SOURCE.json']):
    content=subprocess.check_output(['git','-C',a.checkout,'show',commit+':temporal/'+name])
    (target/name).parent.mkdir(parents=True,exist_ok=True)
    (target/name).write_bytes(content)
    manifest['files'][name]=hashlib.sha256(content).hexdigest()
manifest['commit']=commit
(target/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Pinned shared Chrono source to',commit)
