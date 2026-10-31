"""Twilio Verify SMS adapter. Never enables customer routes or issues sessions.

Provider acceptance is pending, not proof of delivery. Only an approved check
bound to the configured account/service and original verification SID is proof.
No local/dev OTP fallback or provider response bodies are exposed.
"""
import os
import re
from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class VerifyConfig:
    account_sid: str
    service_sid: str
    api_key_sid: str = field(repr=False)
    api_key_secret: str = field(repr=False)

    @classmethod
    def from_environment(cls):
        values = [os.environ.get(k, '').strip() for k in (
            'TWILIO_ACCOUNT_SID', 'TWILIO_VERIFY_SERVICE_SID',
            'TWILIO_API_KEY_SID', 'TWILIO_API_KEY_SECRET')]
        for value, prefix in zip(values[:3], ('AC', 'VA', 'SK')):
            if not re.fullmatch(prefix + r'[0-9a-fA-F]{32}', value):
                return None
        if not values[3]:
            return None
        return cls(*values)


class TwilioSmsVerification:
    def __init__(self, config, *, post=None):
        self.config = config
        self._post = post or httpx.post

    def _request(self, resource, data):
        try:
            response = self._post(
                f'https://verify.twilio.com/v2/Services/{self.config.service_sid}/{resource}',
                data=data, auth=(self.config.api_key_sid, self.config.api_key_secret),
                timeout=10.0, follow_redirects=False,
            )
            if response.status_code == 429:
                return {'error': 'Verification rate limit reached. Try again later.', 'reason': 'rate_limited'}
            if response.status_code == 404:
                return {'error': 'Verification expired or is no longer available.', 'reason': 'expired'}
            if response.status_code not in (200, 201):
                return {'error': 'Verification provider is unavailable.', 'reason': 'provider_unavailable'}
            result = response.json()
            if (not isinstance(result, dict) or
                    result.get('account_sid') != self.config.account_sid or
                    result.get('service_sid') != self.config.service_sid or
                    not re.fullmatch(r'VE[0-9a-fA-F]{32}', str(result.get('sid', '')))):
                return {'error': 'Verification response could not be validated.', 'reason': 'invalid_response'}
            return result
        except (httpx.HTTPError, ValueError, TypeError):
            return {'error': 'Verification provider is unavailable.', 'reason': 'provider_unavailable'}

    def start(self, phone):
        if not isinstance(phone, str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
            return {'error': 'Use a phone number with country code.', 'reason': 'invalid_phone'}
        result = self._request('Verifications', {'To': phone, 'Channel': 'sms'})
        if 'error' in result:
            return result
        if result.get('to') != phone or result.get('channel') != 'sms' or result.get('status') != 'pending':
            return {'error': 'Verification request was not accepted.', 'reason': 'invalid_response'}
        return {'provider': 'twilio_verify', 'verification_sid': result['sid'], 'status': 'pending', 'verified': False}

    def check(self, verification_sid, code):
        if (not isinstance(verification_sid, str) or not re.fullmatch(r'VE[0-9a-fA-F]{32}', verification_sid) or
                not isinstance(code, str) or not re.fullmatch(r'[0-9]{4,10}', code)):
            return {'error': 'Invalid verification code or request.', 'reason': 'invalid_input'}
        result = self._request('VerificationCheck', {'VerificationSid': verification_sid, 'Code': code})
        if 'error' in result:
            return result
        if result['sid'] != verification_sid or result.get('channel') != 'sms':
            return {'error': 'Verification response did not match the request.', 'reason': 'invalid_response'}
        approved = result.get('status') == 'approved' and result.get('valid') is True
        return {'provider': 'twilio_verify', 'verification_sid': verification_sid,
                'status': 'approved' if approved else 'not_verified', 'verified': approved}
