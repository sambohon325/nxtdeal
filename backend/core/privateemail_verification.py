"""Private Email verification mail over authenticated TLS; no general broadcast adapter."""
import os
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


def valid_address(value):
    return (isinstance(value, str) and len(value) <= 254 and
            re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}", value) is not None)


@dataclass(frozen=True)
class PrivateEmailConfig:
    username: str
    password: str = field(repr=False)

    @classmethod
    def from_environment(cls):
        username = os.environ.get('NXTDEAL_PRIVATEEMAIL_USERNAME', '').strip()
        password = os.environ.get('NXTDEAL_PRIVATEEMAIL_PASSWORD', '')
        if not valid_address(username) or not password:
            return None
        return cls(username, password)


class PrivateEmailVerification:
    def __init__(self, config, *, smtp_factory=None):
        self.config = config
        self._smtp_factory = smtp_factory or smtplib.SMTP_SSL

    def send_code(self, recipient, code):
        if not valid_address(recipient) or not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
            return {'error': 'Invalid verification email request.', 'reason': 'invalid_input'}
        message = EmailMessage()
        message['From'] = self.config.username
        message['To'] = recipient
        message['Subject'] = 'Your NXTDeal verification code'
        message['Date'] = formatdate(localtime=False)
        message['Message-ID'] = make_msgid(domain=self.config.username.split('@')[1])
        message.set_content(f'Your NXTDeal verification code is {code}.\n\n'
                            'It expires in 10 minutes. Do not share this code.\n'
                            'If you did not request it, you can ignore this email.\n')
        smtp = None
        try:
            smtp = self._smtp_factory('mail.privateemail.com', 465, timeout=10,
                                      context=ssl.create_default_context())
            smtp.login(self.config.username, self.config.password)
            refused = smtp.send_message(message, from_addr=self.config.username, to_addrs=[recipient])
            if refused:
                return {'error': 'Verification email was not accepted.', 'reason': 'recipient_rejected'}
            return {'provider': 'privateemail', 'delivery': 'accepted', 'verified': False}
        except (smtplib.SMTPException, OSError):
            # A lost acknowledgement can mean acceptance is unknown. Never retry
            # automatically or claim delivery; never expose SMTP responses/secrets.
            return {'error': 'Email acceptance could not be confirmed. Check your inbox before retrying.',
                    'reason': 'acceptance_unconfirmed'}
        finally:
            if smtp is not None:
                try:
                    smtp.close()
                except (smtplib.SMTPException, OSError):
                    pass
