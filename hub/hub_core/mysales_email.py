"""Single-use email proof and recovery; no tokens in URLs, logs or API responses."""
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field


def configured():
    return (os.getenv('NXTDEAL_MYSALES_EMAIL_ENABLED') == 'true'
            and bool(os.getenv('NXTDEAL_MYSALES_SMTP_USERNAME'))
            and bool(os.getenv('NXTDEAL_MYSALES_SMTP_PASSWORD')))


def send_email(address, purpose, token):
    message = EmailMessage()
    message['From'] = os.environ['NXTDEAL_MYSALES_SMTP_USERNAME']
    message['To'] = address
    action = 'verify your email' if purpose == 'verify' else 'reset your password'
    message['Subject'] = 'MySales email verification' if purpose == 'verify' else 'MySales password recovery'
    message.set_content(f'To {action}, paste this code into MySales:\n\n{token}\n\n'
                        'This code expires in 15 minutes and can be used once. '
                        'If you did not request this, ignore this email. Never share this code.')
    with smtplib.SMTP_SSL('mail.privateemail.com', 465, timeout=10, context=ssl.create_default_context()) as smtp:
        smtp.login(os.environ['NXTDEAL_MYSALES_SMTP_USERNAME'], os.environ['NXTDEAL_MYSALES_SMTP_PASSWORD'])
        if smtp.send_message(message):
            raise RuntimeError('Recipient refused')


def deliver(address, purpose):
    from hub_core import mysales_personal as personal
    # Background execution keeps the public response independent of account existence
    # and SMTP timing. Unknown accounts never cause outbound mail.
    with personal.database() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT id FROM accounts WHERE email=?', (address,)).fetchone()
        if not row:
            return
        token = secrets.token_urlsafe(32)
        con.execute('DELETE FROM email_challenges WHERE expires<=? OR (account=? AND purpose=?)',
                    (time.time(), row['id'], purpose))
        con.execute('INSERT INTO email_challenges VALUES (?,?,?,?)',
                    (personal.digest(token), row['id'], purpose, time.time()+900))
    try:
        send_email(address, purpose, token)
    except Exception:
        # Never retry an ambiguous SMTP acknowledgement or disclose its exception.
        with personal.database() as con:
            con.execute('DELETE FROM email_challenges WHERE hash=?', (personal.digest(token),))


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class Proof(BaseModel):
    code: str = Field(min_length=20, max_length=100)


class Recovery(Proof):
    password: str = Field(min_length=12, max_length=256)


def consume(con, code, purpose, owner=None):
    from hub_core import mysales_personal as personal
    row = con.execute('SELECT account FROM email_challenges WHERE hash=? AND purpose=? AND expires>?',
                      (personal.digest(code), purpose, time.time())).fetchone()
    if not row or (owner is not None and row['account'] != owner):
        raise HTTPException(400, 'This code is invalid or expired. Request a new code.')
    con.execute('DELETE FROM email_challenges WHERE hash=?', (personal.digest(code),))
    return row['account']


def install(router):
    from hub_core import mysales_personal as personal
    @router.get('/email/status')
    def status():
        return {'available': bool(configured())}

    @router.post('/password/request', status_code=202)
    def request_reset(body: EmailRequest, request: Request, tasks: BackgroundTasks):
        email = personal.email_key(body.email)
        personal.throttle(request, 'recovery:'+email)
        if not configured():
            raise HTTPException(503, 'Email recovery is not available yet.')
        tasks.add_task(deliver, email, 'reset')
        return {'message': 'If this account exists, a recovery code will be sent. Check your inbox and spam folder.'}

    @router.post('/email/request', status_code=202)
    def request_verification(request: Request, tasks: BackgroundTasks, owner=Depends(personal.account)):
        personal.throttle(request, 'verification:'+owner['id'])
        if not configured():
            raise HTTPException(503, 'Email verification is not available yet.')
        tasks.add_task(deliver, owner['email'], 'verify')
        return {'message': 'Verification requested. Check your inbox and spam folder.'}

    @router.post('/email/verify')
    def verify(body: Proof, request: Request, owner=Depends(personal.account)):
        personal.throttle(request, 'proof:'+owner['id'])
        with personal.database() as con:
            con.execute('BEGIN IMMEDIATE')
            consume(con, body.code, 'verify', owner['id'])
            con.execute('INSERT OR REPLACE INTO verified_emails VALUES (?,?)', (owner['id'], time.time()))
        return {'email_verified': True}

    @router.post('/password/reset')
    def reset(body: Recovery, request: Request):
        personal.throttle(request, 'reset-proof:'+personal.digest(body.code))
        salt, password_hash = personal.hash_password(body.password)
        with personal.database() as con:
            con.execute('BEGIN IMMEDIATE')
            owner = consume(con, body.code, 'reset')
            con.execute('UPDATE accounts SET salt=?,hash=? WHERE id=?', (salt, password_hash, owner))
            con.execute('DELETE FROM sessions WHERE account=?', (owner,))
            con.execute('DELETE FROM email_challenges WHERE account=?', (owner,))
            con.execute('INSERT OR REPLACE INTO verified_emails VALUES (?,?)', (owner, time.time()))
            # Optional assistant tables may not exist on a personal-only deployment.
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'assistant_grants' in tables:
                con.execute('UPDATE assistant_grants SET revoked=1 WHERE owner=?', (owner,))
            if 'assistant_requests' in tables:
                con.execute('DELETE FROM assistant_requests WHERE owner=?', (owner,))
        return {'message': 'Password updated. Sign in again. All sessions and assistant connections have been revoked.'}
