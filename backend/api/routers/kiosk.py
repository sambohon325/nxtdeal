"""Opt-in router factory. Deliberately not included in the running application."""
import json

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from api.deps import _bearer_token
from core import auth
from core.kiosk_request_limit import KioskRequestLimit
from core.kiosk_checkin import KioskCheckin, CheckinConflict, CheckinThrottled, CheckinUnconfirmed


MAX_BODY_BYTES = 4096


def _response(body, status=200, headers=None):
    return JSONResponse(body, status_code=status,
                        headers={'Cache-Control': 'no-store', **(headers or {})})


def _error(code, status):
    # Never echo request values, bearer tokens or internal exception details.
    return _response({'error': code}, status)


class _BodyError(Exception):
    def __init__(self, code, status):
        self.code, self.status = code, status


async def _body(request):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise _BodyError('json_required', 415)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise _BodyError('request_too_large', 413)
        chunks.append(chunk)

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('Invalid JSON constant')

    try:
        body = json.loads(b''.join(chunks), object_pairs_hook=object_pairs,
                          parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise _BodyError('invalid_json', 400) from None
    if not isinstance(body, dict):
        raise _BodyError('invalid_fields', 422)
    return body


def _staff_error(token):
    payload = auth.verify_token(token)
    if not payload or auth.is_mfa_challenge_token(payload):
        return _error('staff_authentication_required', 401)
    if payload.get('role') != 'ADMIN':
        return _error('administrator_required', 403)
    return None


def create_kiosk_router(sessions, *, enabled=False, checkin=None):
    router = APIRouter(prefix='/kiosk')
    if not enabled:
        return router
    adapter = checkin or KioskCheckin(sessions)
    admission = KioskRequestLimit()
    if adapter.sessions is not sessions:
        raise ValueError('Kiosk adapter must use this server-owned session registry')

    async def manage(request, revoke=False):
        if not admission.allow(request.client.host if request.client else None):
            return _response({'error': 'kiosk_request_limit'}, 429, {'Retry-After': '60'})
        token = _bearer_token(request.headers.get('authorization'))
        denied = _staff_error(token)
        if denied is not None:
            return denied
        try:
            body = await _body(request)
            if set(body) != {'device_id'}:
                return _error('invalid_fields', 422)
            if revoke:
                await run_in_threadpool(sessions.revoke, token, body['device_id'])
                return _response({'status': 'revoked'})
            grant = await run_in_threadpool(sessions.issue, token, body['device_id'])
            return _response(grant, 201)
        except _BodyError as error:
            return _error(error.code, error.status)
        except PermissionError:
            return _error('staff_authentication_required', 401)
        except ValueError:
            return _error('invalid_fields', 422)
        except RuntimeError:
            return _error('enrollment_unavailable', 503)

    @router.post('/enroll')
    async def enroll(request: Request):
        return await manage(request)

    @router.post('/revoke')
    async def revoke(request: Request):
        return await manage(request, revoke=True)

    @router.post('/checkin')
    async def check_in(request: Request):
        if not admission.allow(request.client.host if request.client else None):
            return _response({'error': 'kiosk_request_limit'}, 429, {'Retry-After': '60'})
        token = _bearer_token(request.headers.get('authorization'))
        if sessions._digest(token) is None:
            return _error('kiosk_authentication_required', 401)
        try:
            body = await _body(request)
            if (set(body) - {'device_id', 'request_id', 'name', 'phone', 'reason'}
                    or not {'device_id', 'request_id', 'name'} <= set(body)):
                return _error('invalid_fields', 422)
            if sessions.verify(token, device_id=body['device_id'], action=sessions.ACTION) is None:
                return _error('kiosk_authentication_required', 401)
            fields = {key: body[key] for key in ('name', 'phone', 'reason') if key in body}
            result = await run_in_threadpool(adapter.submit, token, device_id=body['device_id'],
                                            request_id=body['request_id'], body=fields)
            return _response(result)
        except _BodyError as error:
            return _error(error.code, error.status)
        except PermissionError:
            return _error('kiosk_authentication_required', 401)
        except CheckinConflict:
            return _error('request_id_conflict', 409)
        except ValueError:
            return _error('invalid_fields', 422)
        except CheckinThrottled:
            return _response({'error': 'checkin_throttled'}, 429, {'Retry-After': '60'})
        except CheckinUnconfirmed:
            return _response({'error': 'checkin_unconfirmed', 'retry_safe': False,
                              'message': 'Ask the front desk before trying again.'}, 503)

    return router
