"""Site-scoped dealer AI credentials. Secrets never enter website graph/snapshots."""
import json, os, re, tempfile
from uuid import uuid4
from pathlib import Path
from hashlib import sha256
from threading import RLock
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from core.storage_paths import storage_dir
from openai import OpenAI
_lock=RLock()

def _cipher():
    key=os.environ.get('DEALEROS_AI_CREDENTIAL_KEY','')
    try:return Fernet(key.encode())
    except Exception:raise ValueError('Secure credential storage is not configured. Contact your NXTDeal administrator.') from None

def _path(site):
    return Path(storage_dir())/'private_ai'/ (sha256(site.encode()).hexdigest()+'.enc')

def _read(site):
    p=_path(site)
    if not p.exists():return None
    try:
        data=json.loads(_cipher().decrypt(p.read_bytes()))
        if data['site']!=site:raise ValueError()
        return data
    except Exception:raise ValueError('Saved credentials cannot be unlocked. Contact your NXTDeal administrator.') from None

def _write(site,data):
    encrypted=_cipher().encrypt(json.dumps(data).encode());p=_path(site);p.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=p.parent,prefix='.pending-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(encrypted);f.flush();os.fsync(f.fileno())
        os.replace(name,p)
    finally:
        if os.path.exists(name):os.unlink(name)

def status(site):
    with _lock:
        data=_read(site)
        return {'provider':'openai','model':data['model'] if data else 'gpt-4o-mini','configured':bool(data),'status':data.get('status','saved') if data else 'not_connected','tested_at':data.get('tested_at') if data else None,'revision':data['revision'] if data else 0}

def save(site,provider,model,key):
    if provider!='openai':raise ValueError('OpenAI is the supported provider for this assistant.')
    if not isinstance(model,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}',model):raise ValueError('Enter a valid model ID.')
    if not isinstance(key,str) or not 10<=len(key)<=512 or any(c.isspace() for c in key):raise ValueError('Enter a valid API key.')
    with _lock:
        old=_read(site)
        _write(site,{'site':site,'provider':provider,'model':model,'key':key,'revision':(old['revision'] if old else 0)+1,'status':'saved','tested_at':None,'generation':uuid4().hex})
        return status(site)

def disconnect(site):
    with _lock:
        p=_path(site)
        if p.exists():p.unlink()
    return status(site)

def _client(data):
    return OpenAI(api_key=data['key'],base_url='https://api.openai.com/v1',timeout=15,max_retries=0)

def test_connection(site):
    with _lock:
        data=_read(site)
    if not data:raise ValueError('Save an API key first.')
    # No inventory, customer records or conversation history in the test request.
    try:
        with _client(data) as client:
            response=client.chat.completions.create(model=data['model'],messages=[{'role':'user','content':'Return JSON with reply_text set to connected.'}],response_format={'type':'json_object'},max_completion_tokens=32)
        parsed=json.loads(response.choices[0].message.content)
        ok=isinstance(parsed.get('reply_text'),str) and bool(parsed['reply_text'].strip())
    except Exception:ok=False
    with _lock:
        latest=_read(site)
        if not latest or latest.get('generation')!=data.get('generation'):raise ValueError('Credentials changed during the test. Test the current connection again.')
        latest.update(status='connected' if ok else 'test_failed',tested_at=datetime.now(timezone.utc).isoformat());_write(site,latest)
        return {**status(site),'message':'Connection verified.' if ok else 'Connection failed. Check the API key, model access, billing and provider availability.'}

def completion(site,**kwargs):
    with _lock:data=_read(site)
    if not data or data.get('status')!='connected':raise ValueError('Dealer API connection is not verified')
    with _client(data) as client:return client.chat.completions.create(model=data['model'],**kwargs)
