"""
Real-time push for Communications (session 28 -- Sam picked real-time over polling when
asked). A genuinely new pattern for this codebase (everything else is request/response
FastAPI routes) -- kept as small and single-purpose as possible: this module only tracks
which employee_ids currently have an open websocket and pushes JSON payloads to them.
Sending a message is still a normal REST POST (core/messaging_api.py); the websocket
exists purely so already-open clients hear about it immediately instead of needing to
poll or refresh.

In-memory only, same as core/dealeros.ledger and every other singleton in this codebase
-- fine for a single-process dev/demo deployment (matches how the whole graph itself is
just an in-memory ledger flushed to storage/graph.json). Would need a pub/sub layer
(Redis, etc.) to work across multiple server processes -- flagged in BUILD_QUEUE.md,
not attempted here.
"""

import asyncio

from starlette.websockets import WebSocketDisconnect

from core.auth import credential_store, verify_token, is_mfa_challenge_token
from core.messaging import can_access_channel


class ConnectionManager:

    SESSION_CHECK_SECONDS = 15

    def __init__(self):
        # employee_id -> list of open WebSocket connections (an employee could have
        # more than one tab/device open at once).
        self.connections = {}
        self._session_tokens = {}

    @staticmethod
    def _session_ready(payload, employee_id):
        if (not payload or is_mfa_challenge_token(payload)
                or payload.get("employee_id") != employee_id):
            return False
        record = credential_store.get_record(employee_id)
        return bool(record and not record.get("must_change_password"))

    async def connect(self, employee_id, websocket, token):
        payload = verify_token(token)
        if not self._session_ready(payload, employee_id):
            await websocket.close(code=4401)
            return False
        await websocket.accept()

        self.connections.setdefault(employee_id, []).append(websocket)
        self._session_tokens[websocket] = token
        return True

    def disconnect(self, employee_id, websocket):
        self._session_tokens.pop(websocket, None)

        sockets = self.connections.get(employee_id)

        if not sockets:
            return

        if websocket in sockets:
            sockets.remove(websocket)

        if not sockets:
            self.connections.pop(employee_id, None)

    async def listen(self, employee_id, websocket):
        """Recheck idle sessions even when no message is broadcast.

        Receives carry no application actions; sends remain authenticated REST
        requests. Cancellation and unexpected disconnect errors must release the
        socket and its retained token as well as ordinary disconnects.
        """
        receiver = None
        try:
            while websocket in self._session_tokens:
                session = verify_token(self._session_tokens.get(websocket))
                if not self._session_ready(session, employee_id):
                    await self._close_connection(employee_id, websocket, 4401)
                    return
                if receiver is None:
                    receiver = asyncio.create_task(websocket.receive())
                # A timeout must not cancel an ASGI receive which may already be
                # delivering the peer's disconnect. Cancel only on final exit.
                done, _ = await asyncio.wait(
                    {receiver}, timeout=self.SESSION_CHECK_SECONDS
                )
                if done:
                    event = receiver.result()
                    receiver = None
                    if event['type'] == 'websocket.disconnect':
                        return
                    # Both text and binary frames are ignored: only REST sends.
        finally:
            self.disconnect(employee_id, websocket)
            if receiver is not None:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)

    async def _close_connection(self, employee_id, websocket, code):
        # Claim teardown synchronously before any transport await. A concurrent
        # listener/broadcast then sees deregistration, not a revoked empty token.
        if websocket not in self._session_tokens:
            return
        self.disconnect(employee_id, websocket)
        try:
            await websocket.close(code=code)
        except (WebSocketDisconnect, OSError, RuntimeError):
            pass  # The peer/transport may already be closed; registration is gone.

    async def send_to_employee(self, employee_id, payload):

        sockets = list(self.connections.get(employee_id, []))

        for socket in sockets:

            if socket not in self._session_tokens:
                continue

            try:
                # Recheck every individual connection, including direct messages.
                # A password reset must not leave an older tab receiving events.
                session = verify_token(self._session_tokens.get(socket))
                if not self._session_ready(session, employee_id):
                    await self._close_connection(employee_id, socket, 4401)
                    continue
                await socket.send_json(payload)
            except Exception:
                await self._close_connection(employee_id, socket, 1011)

    async def broadcast_channel_message(self, channel_key, payload):
        """Every currently-connected employee whose role can see this channel (ADMIN
        included via can_access_channel's own ADMIN-always-passes rule) -- not every
        employee with a credential, since there's no point pushing to someone who isn't
        even connected."""

        for employee_id in list(self.connections.keys()):

            record = credential_store.get_record(employee_id)

            if not record:
                continue

            if can_access_channel(record["role"], channel_key):
                await self.send_to_employee(employee_id, payload)

    async def broadcast_direct_message(self, sender_id, recipient_id, payload):

        await self.send_to_employee(sender_id, payload)

        if recipient_id != sender_id:
            await self.send_to_employee(recipient_id, payload)

    def reset(self):
        """Used by tests -- clears all tracked connections without touching anything
        else, same reset()-in-place pattern core/dealeros.ledger and core/auth.py's
        CredentialStore already use."""

        self.connections = {}
        self._session_tokens = {}


manager = ConnectionManager()
