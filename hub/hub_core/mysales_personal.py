"""Personal MySales accounts. Deliberately separate from Hub admins and tenant staff.
Opaque sessions are hashed at rest; all personal rows are scoped to the account.
Activation requires an explicit persistent database path. Email delivery is opt-in.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from hub_core.auth import hash_password, verify_password

router = APIRouter(prefix='/mysales', tags=['Personal MySales'])
TTL = 60 * 60 * 12

@contextmanager
def database():
    path = os.getenv('NXTDEAL_MYSALES_DB', '')
    if os.getenv('NXTDEAL_MYSALES_ENABLED') != 'true' or not path or not Path(path).is_absolute():
        raise HTTPException(503, 'Personal MySales accounts are not available yet.')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA foreign_keys=ON')
        con.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, account TEXT REFERENCES accounts(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, account TEXT REFERENCES accounts(id), kind TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS records_owner ON records(account,kind);
        CREATE TABLE IF NOT EXISTS pages(account TEXT PRIMARY KEY REFERENCES accounts(id), slug TEXT UNIQUE NOT NULL, draft TEXT NOT NULL, published TEXT);
        CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS verified_emails(account TEXT PRIMARY KEY REFERENCES accounts(id), verified REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS email_challenges(hash TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(id), purpose TEXT NOT NULL, expires REAL NOT NULL);
        ''')
        os.chmod(path, 0o600)
        yield con
        con.commit()
    finally:
        con.close()

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def throttle(request, identity):
    # Trust the direct peer, never caller-controlled forwarded headers. A shared proxy
    # gets the global ceiling; per-identity budgets survive restarts and worker changes.
    now = time.time()
    with database() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('DELETE FROM limits WHERE expires <= ?', (now,))
        for key, maximum in [('peer:'+str(request.client.host if request.client else 'unknown'),120), ('identity:'+identity,10)]:
            key = digest(key)
            row = con.execute('SELECT count FROM limits WHERE key=?', (key,)).fetchone()
            if row and row['count'] >= maximum:
                raise HTTPException(429, 'Too many attempts. Try again in a few minutes.', headers={'Retry-After':'600'})
            con.execute('INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key,now+600))

def email_key(email):
    email = email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422,'Enter a valid email address.')
    return email

class Login(BaseModel):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=1,max_length=256)
class Signup(Login):
    name: str = Field(min_length=1,max_length=100)

def session(con, account):
    token=secrets.token_urlsafe(48)
    con.execute('DELETE FROM sessions WHERE expires <= ?', (time.time(),))
    con.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(token),account['id'],time.time()+TTL))
    con.execute('DELETE FROM sessions WHERE account=? AND hash NOT IN (SELECT hash FROM sessions WHERE account=? ORDER BY expires DESC LIMIT 20)',(account['id'],account['id']))
    verified = con.execute('SELECT 1 FROM verified_emails WHERE account=?',(account['id'],)).fetchone() is not None
    return {'token':token,'account':{'id':account['id'],'name':account['name'],'email':account['email'],'email_verified':verified}}

@router.post('/signup')
def signup(body: Signup, request: Request):
    email=email_key(body.email); throttle(request,email)
    if len(body.password)<12 or not body.name.strip():
        raise HTTPException(422,'Use a name and a password of at least 12 characters.')
    salt,password_hash=hash_password(body.password)
    with database() as con:
        try:
            con.execute('INSERT INTO accounts VALUES (?,?,?,?,?,?)', (secrets.token_hex(16),email,body.name.strip(),salt,password_hash,time.time(),))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Unable to create this account. Try signing in instead.')
        return session(con,con.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone())

@router.post('/login')
def login(body: Login, request: Request):
    email=email_key(body.email); throttle(request,email)
    with database() as con:
        # Serialize credential validation/session creation with password recovery.
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone()
        valid=verify_password(body.password,row['salt'] if row else '00'*16,row['hash'] if row else '00'*32)
        if not row or not valid: raise HTTPException(401,'Email or password is incorrect.')
        return session(con,row)

def account(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Sign in to MySales.')
    with database() as con:
        row=con.execute('SELECT a.id,a.email,a.name FROM accounts a JOIN sessions s ON a.id=s.account WHERE s.hash=? AND s.expires>?',(digest(authorization[7:]),time.time())).fetchone()
        if not row: raise HTTPException(401,'Sign in to MySales.')
        return dict(row)

@router.get('/me')
def me(owner=Depends(account)):
    with database() as con:
        verified=con.execute('SELECT 1 FROM verified_emails WHERE account=?',(owner['id'],)).fetchone() is not None
    return dict(owner,email_verified=verified)

@router.post('/logout')
def logout(owner=Depends(account), authorization: str=Header(default='')):
    with database() as con: con.execute('DELETE FROM sessions WHERE hash=? AND account=?',(digest(authorization[7:]),owner['id']))
    return {'ok':True}

class Record(BaseModel):
    title: str = Field(min_length=1,max_length=160)
    notes: str = Field(default='',max_length=4000)
    email: str = Field(default='',max_length=254)
    phone: str = Field(default='',max_length=40)
    due: str = Field(default='',max_length=10)
    done: bool = False
    stage: str = Field(default='new',pattern='^(new|contacted|appointment|sold|closed)$')

def kind_check(kind):
    if kind not in ('contacts','tasks'): raise HTTPException(404,'Not found.')

def checked(body):
    if not body.title.strip(): raise HTTPException(422,'A name or title is required.')
    if body.due:
        from datetime import date
        try: date.fromisoformat(body.due)
        except ValueError: raise HTTPException(422,'Use a valid due date.')
    return body.model_dump()

@router.get('/records/{kind}')
def records(kind: str,owner=Depends(account)):
    kind_check(kind)
    with database() as con:
        return {'items':[dict(id=r['id'],**json.loads(r['data'])) for r in con.execute('SELECT id,data FROM records WHERE account=? AND kind=? ORDER BY updated DESC',(owner['id'],kind))]}

@router.post('/records/{kind}')
def create(kind: str,body: Record,owner=Depends(account)):
    kind_check(kind); data=checked(body); ident=secrets.token_hex(16)
    with database() as con:
        count=con.execute('SELECT count(*) FROM records WHERE account=?',(owner['id'],)).fetchone()[0]
        if count>=10000: raise HTTPException(409,'Account record limit reached.')
        con.execute('INSERT INTO records VALUES (?,?,?,?,?)',(ident,owner['id'],kind,json.dumps(data),time.time()))
    return dict(id=ident,**data)

@router.put('/records/{kind}/{ident}')
def update(kind: str,ident: str,body: Record,owner=Depends(account)):
    kind_check(kind);data=checked(body)
    with database() as con:
        cursor=con.execute('UPDATE records SET data=?,updated=? WHERE id=? AND account=? AND kind=?',(json.dumps(data),time.time(),ident,owner['id'],kind))
        if cursor.rowcount!=1: raise HTTPException(404,'Not found.')
    return dict(id=ident,**data)

class Connection(BaseModel):
    dealership: str=Field(min_length=1,max_length=100)

def resolve_connection(identifier):
    from hub_core.dealer_registry import registry
    dealer=registry.get(identifier.strip().upper()) or registry.get_by_slug(identifier.strip())
    if not dealer or dealer.status not in ('active','trial','expansion','churn_risk'):
        raise HTTPException(404,'This dealership is not available on NXTDeal.')
    from hub_core.dealers_api import resolve_dealer_api
    resolved=resolve_dealer_api(dealer.dealer_id)
    if 'error' in resolved: raise HTTPException(409,'This dealership is not available online.')
    from urllib.parse import urlsplit
    url=resolved['api_base_url']; parsed=urlsplit(url)
    # No arbitrary URL or staff token may be supplied by the salesperson.
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(409,'The dealership inventory address is not configured securely.')
    data={'dealer_id':dealer.dealer_id,'name':dealer.name,'api_base_url':url}
    return data

@router.put('/inventory-connection')
def connect(body:Connection,owner=Depends(account)):
    data=resolve_connection(body.dealership)
    with database() as con:
        con.execute('DELETE FROM records WHERE account=? AND kind=?',(owner['id'],'connection'))
        con.execute('INSERT INTO records VALUES (?,?,?,?,?)',(secrets.token_hex(16),owner['id'],'connection',json.dumps({'dealer_id':data['dealer_id']}),time.time()))
    return data

@router.get('/inventory-connection')
def connection(owner=Depends(account)):
    with database() as con: row=con.execute('SELECT data FROM records WHERE account=? AND kind=?',(owner['id'],'connection')).fetchone()
    if not row:return None
    # Re-resolve every read so a suspended or relocated tenant cannot leave a stale origin.
    return resolve_connection(json.loads(row['data'])['dealer_id'])

@router.delete('/inventory-connection')
def disconnect(owner=Depends(account)):
    with database() as con: con.execute('DELETE FROM records WHERE account=? AND kind=?',(owner['id'],'connection'))
    return {'ok':True}


class PersonalPageDraft(BaseModel):
    headline: str = Field(default='', max_length=160)
    subheadline: str = Field(default='', max_length=200)
    bio: str = Field(default='', max_length=3000)
    photo_url: str = Field(default='', max_length=1000)
    phone: str = Field(default='', max_length=40)
    email: str = Field(default='', max_length=254)
    calendar_link: str = Field(default='', max_length=1000)
    review_link: str = Field(default='', max_length=1000)

    @field_validator('photo_url', 'calendar_link', 'review_link')
    @classmethod
    def https_only(cls, value):
        from urllib.parse import urlsplit
        if not value: return value
        parsed = urlsplit(value)
        if any(ord(c) <= 32 or ord(c) == 127 for c in value) or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use an HTTPS URL without embedded credentials.')
        return value

    @field_validator('email')
    @classmethod
    def contact_email(cls, value):
        if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid contact email.')
        return value


def page_view(row):
    return {'slug':row['slug'], 'draft':json.loads(row['draft']), 'published':row['published'] is not None}

@router.get('/page')
def personal_page(owner=Depends(account)):
    with database() as con:
        row=con.execute('SELECT * FROM pages WHERE account=?',(owner['id'],)).fetchone()
        if not row:
            return {'slug':owner['id'],'draft':PersonalPageDraft(headline=owner['name']).model_dump(),'published':False}
        return page_view(row)

@router.put('/page')
def save_personal_page(body:PersonalPageDraft,owner=Depends(account)):
    # Saving a draft never modifies an already published snapshot.
    with database() as con:
        con.execute('INSERT INTO pages(account,slug,draft,published) VALUES (?,?,?,NULL) ON CONFLICT(account) DO UPDATE SET draft=excluded.draft', (owner['id'],owner['id'],json.dumps(body.model_dump())))
        return page_view(con.execute('SELECT * FROM pages WHERE account=?',(owner['id'],)).fetchone())

class PagePublication(BaseModel):
    published: bool

@router.put('/page/publication')
def publish_personal_page(body:PagePublication,owner=Depends(account)):
    with database() as con:
        row=con.execute('SELECT * FROM pages WHERE account=?',(owner['id'],)).fetchone()
        if not row: raise HTTPException(409,'Save your page before publishing.')
        if body.published and not json.loads(row['draft'])['headline'].strip():
            raise HTTPException(422,'Add a headline before publishing.')
        con.execute('UPDATE pages SET published=? WHERE account=?',(row['draft'] if body.published else None,owner['id']))
        return page_view(con.execute('SELECT * FROM pages WHERE account=?',(owner['id'],)).fetchone())

@router.get('/public/pages/{slug}')
def public_personal_page(slug:str):
    with database() as con:
        row=con.execute('SELECT slug,published FROM pages WHERE slug=? AND published IS NOT NULL',(slug,)).fetchone()
        if not row: raise HTTPException(404,'This page is not published.')
        data=PersonalPageDraft(**json.loads(row['published'])).model_dump()
        return dict(data,slug=row['slug'],cta_text='Contact me',featured_vehicles=[],branding={'branding_mode':'personal','oem_name':None,'oem_logo_url':None})


from hub_core.mysales_email import install as install_email_routes
install_email_routes(router)
