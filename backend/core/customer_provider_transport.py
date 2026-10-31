"""Credential-free TLS connectivity evidence; never authenticates or sends messages.

Run from backend with python -m core.customer_provider_transport. Results describe
this machine at the observation time, not production delivery or provider readiness.
"""
from datetime import datetime, timezone
import json
import socket
import ssl

ENDPOINTS = (('privateemail', 'mail.privateemail.com', 465),
             ('twilio_verify', 'verify.twilio.com', 443))


def check_transport():
    results = []
    for provider, host, port in ENDPOINTS:
        row = {'provider': provider, 'host': host, 'port': port,
               'observed_at': datetime.now(timezone.utc).isoformat(),
               'authentication_tested': False, 'delivery_tested': False}
        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=10) as connection:
                with context.wrap_socket(connection, server_hostname=host) as secure:
                    row.update(tls_verified=True, tls_version=secure.version())
        except ssl.SSLCertVerificationError:
            row.update(tls_verified=False, reason='certificate_verification_failed')
        except (OSError, ssl.SSLError):
            # Do not print raw network/provider exception details.
            row.update(tls_verified=False, reason='connection_unconfirmed')
        results.append(row)
    return {'scope': 'executing_host_only', 'endpoints': results}


if __name__ == '__main__':
    print(json.dumps(check_transport(), indent=2))
