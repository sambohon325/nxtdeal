"""ASGI socket lifecycle regressions, with no network or provider access."""
import asyncio
from copy import deepcopy

import pytest
from starlette.websockets import WebSocket

from core import auth
from core.ws_manager import ConnectionManager


@pytest.fixture(autouse=True)
def fictional_staff():
    previous = deepcopy(auth.credential_store.credentials)
    auth.credential_store.reset()
    auth.credential_store.set_credential('SYN-SOCKET', 'FictionalSocket2026!', 'SALES', must_change_password=False)
    yield
    auth.credential_store.load_credentials(previous)


class Transport:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait({'type': 'websocket.connect'})
        self.sent = []
        self.receiving = asyncio.Event()
        self.closing = asyncio.Event()
        self.allow_close = asyncio.Event()
        self.allow_close.set()
        self.disconnect_consumed = asyncio.Event()
        self.allow_disconnect = asyncio.Event()
        self.allow_disconnect.set()
        self.cancelled_receives = 0
        self.fail_send = False
        self.socket = WebSocket({'type': 'websocket', 'path': '/ws/messaging'},
                                self.receive, self.send)

    async def receive(self):
        self.receiving.set()
        try:
            event = await self.incoming.get()
            if event['type'] == 'websocket.disconnect':
                self.disconnect_consumed.set()
                await self.allow_disconnect.wait()
            return event
        except asyncio.CancelledError:
            self.cancelled_receives += 1
            raise

    async def send(self, event):
        if self.fail_send and event['type'] == 'websocket.send':
            if self.fail_send == 'closed':
                raise OSError('Fictional closed transport')
            raise RuntimeError('Fictional send failure')
        self.sent.append(event)
        if event['type'] == 'websocket.close':
            self.closing.set()
            await self.allow_close.wait()

    @property
    def closes(self):
        return [event['code'] for event in self.sent if event['type'] == 'websocket.close']


async def connected(manager, transport):
    role = auth.credential_store.get_record('SYN-SOCKET')['role']
    token = auth.issue_token('SYN-SOCKET', role)
    assert await manager.connect('SYN-SOCKET', transport.socket, token)
    transport.receiving.clear()
    return asyncio.create_task(manager.listen('SYN-SOCKET', transport.socket))


def test_broadcast_revocation_claims_close_before_awaiting_transport():
    async def scenario():
        manager, transport = ConnectionManager(), Transport()
        manager.SESSION_CHECK_SECONDS = 0.01
        listener = await connected(manager, transport)
        await asyncio.wait_for(transport.receiving.wait(), 10)
        transport.allow_close.clear()
        auth.credential_store.set_role('SYN-SOCKET', 'SERVICE')
        sender = asyncio.create_task(manager.send_to_employee('SYN-SOCKET', {'event': 'denied'}))
        # Yield so the sender task can run its disconnect before the listen
        # loop's SESSION_CHECK_SECONDS timer fires. On slow CI runners the
        # 10ms timer can expire first, causing listen() to block inside
        # _close_connection -> websocket.close -> allow_close.wait() before
        # the sender has a chance to disconnect the socket.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        try:
            await asyncio.wait_for(transport.closing.wait(), 10)
            # Close frame was claimed (closing set) while the transport
            # handshake was still blocked (allow_close cleared). Release
            # the handshake so whichever task is pending inside
            # _close_connection's websocket.close() can finish. On shared
            # CI runners the listen loop's 10ms session-check can fire
            # before the broadcast sender, making listen() block there.
            transport.allow_close.set()
            await asyncio.wait_for(listener, 10)
            assert transport.closes == [4401]
            assert not manager.connections and not manager._session_tokens
        finally:
            transport.allow_close.set()
            await asyncio.gather(sender, return_exceptions=True)
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('already_closed', [False, True])
def test_failed_delivery_does_not_masquerade_as_revoked_auth(already_closed):
    async def scenario():
        manager, transport = ConnectionManager(), Transport()
        manager.SESSION_CHECK_SECONDS = 0.01
        listener = await connected(manager, transport)
        await asyncio.wait_for(transport.receiving.wait(), 10)
        transport.fail_send = 'closed' if already_closed else True
        await manager.send_to_employee('SYN-SOCKET', {'event': 'failed'})
        await asyncio.wait_for(listener, 10)
        assert transport.closes == ([] if already_closed else [1011])
        assert not manager.connections and not manager._session_tokens
    asyncio.run(scenario())


def test_idle_recheck_does_not_cancel_partially_delivered_disconnect():
    async def scenario():
        manager, transport = ConnectionManager(), Transport()
        manager.SESSION_CHECK_SECONDS = 0.01
        transport.allow_disconnect.clear()
        listener = await connected(manager, transport)
        transport.incoming.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
        try:
            await asyncio.wait_for(transport.disconnect_consumed.wait(), 10)
            # Deliberately span multiple recheck deadlines while ASGI is delivering.
            await asyncio.sleep(0.04)
            assert transport.cancelled_receives == 0
            transport.allow_disconnect.set()
            await asyncio.wait_for(listener, 10)
            assert not manager.connections and not manager._session_tokens
        finally:
            transport.allow_disconnect.set()
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
    asyncio.run(scenario())


def test_text_and_binary_frames_are_ignored_then_disconnect_releases_session():
    async def scenario():
        manager, transport = ConnectionManager(), Transport()
        listener = await connected(manager, transport)
        for event in (
            {'type': 'websocket.receive', 'text': 'not an application command'},
            {'type': 'websocket.receive', 'bytes': b'fictional binary'},
            {'type': 'websocket.disconnect', 'code': 1000},
        ):
            transport.incoming.put_nowait(event)
        await asyncio.wait_for(listener, 10)
        assert not transport.closes
        assert not manager.connections and not manager._session_tokens
    asyncio.run(scenario())


def test_idle_revocation_closes_only_stale_tab_while_fresh_login_receives():
    async def scenario():
        manager, old, fresh = ConnectionManager(), Transport(), Transport()
        manager.SESSION_CHECK_SECONDS = 0.01
        stale_listener = await connected(manager, old)
        await asyncio.wait_for(old.receiving.wait(), 10)
        old.allow_close.clear()
        auth.credential_store.set_role('SYN-SOCKET', 'SERVICE')
        fresh_listener = await connected(manager, fresh)
        try:
            await asyncio.wait_for(old.closing.wait(), 10)
            # Idle listener owns the pending close. Broadcast must not close it
            # again, and must still deliver to the replacement login.
            await manager.send_to_employee('SYN-SOCKET', {'event': 'fresh-only'})
            assert old.closes == [4401]
            assert not any(event['type'] == 'websocket.send' for event in old.sent)
            assert not fresh.closes
            assert any(event.get('text') == '{"event":"fresh-only"}' for event in fresh.sent)
            assert manager.connections == {'SYN-SOCKET': [fresh.socket]}
            assert set(manager._session_tokens) == {fresh.socket}
            old.allow_close.set()
            await asyncio.wait_for(stale_listener, 10)
            fresh.incoming.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
            await asyncio.wait_for(fresh_listener, 10)
            assert not manager.connections and not manager._session_tokens
        finally:
            old.allow_close.set()
            stale_listener.cancel()
            fresh_listener.cancel()
            await asyncio.gather(stale_listener, fresh_listener, return_exceptions=True)
    asyncio.run(scenario())


def test_temporary_password_rejected_before_socket_accept():
    async def scenario():
        manager, transport = ConnectionManager(), Transport()
        auth.credential_store.get_record('SYN-SOCKET')['must_change_password'] = True
        token = auth.issue_token('SYN-SOCKET', 'SALES')
        assert not await manager.connect('SYN-SOCKET', transport.socket, token)
        assert transport.closes == [4401]
        assert not any(event['type'] == 'websocket.accept' for event in transport.sent)
        assert not manager.connections and not manager._session_tokens
    asyncio.run(scenario())


@pytest.mark.parametrize('trigger', ['idle', 'broadcast'])
def test_password_change_requirement_closes_existing_socket(trigger):
    async def scenario():
        manager, transport = ConnectionManager(), Transport()
        manager.SESSION_CHECK_SECONDS = 0.01
        listener = await connected(manager, transport)
        try:
            await asyncio.wait_for(transport.receiving.wait(), 1)
            # A policy flag change must be enforced even without a new password hash.
            auth.credential_store.get_record('SYN-SOCKET')['must_change_password'] = True
            if trigger == 'broadcast':
                await manager.send_to_employee('SYN-SOCKET', {'event': 'must-not-deliver'})
            await asyncio.wait_for(listener, 1)
            assert transport.closes == [4401]
            assert not any(event['type'] == 'websocket.send' for event in transport.sent)
            assert not manager.connections and not manager._session_tokens
        finally:
            if not listener.done():
                listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
    asyncio.run(scenario())
