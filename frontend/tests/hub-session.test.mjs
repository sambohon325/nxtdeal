import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const code = ts.transpileModule(fs.readFileSync(new URL('../lib/hubApi.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

function harness(responses) {
  const storage = new Map();
  const requests = [];
  const scope = {
    exports: {}, window: {}, process: { env: { NEXT_PUBLIC_HUB_API_URL: 'http://127.0.0.1:9000' } },
    sessionStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    require: name => {
      assert.equal(name, './canonicalApiUrl');
      return { canonicalApiUrl: value => value };
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      const next = responses.shift();
      assert.ok(next, 'Unexpected API request');
      return { status: next.status, ok: next.status >= 200 && next.status < 300, json: async () => next.body };
    },
  };
  vm.runInNewContext(code, scope);
  scope.exports.setStoredHubToken('old-fictional-token');
  return { api: scope.exports, requests };
}

test('password change replaces token before the next protected request', async () => {
  const { api, requests } = harness([
    { status: 200, body: { ok: true, token: 'replacement-fictional-token' } },
    { status: 200, body: { employee_id: 'fictional-admin', role: 'ADMIN' } },
  ]);
  await api.hubChangePassword('old-fictional-password', 'new-fictional-password');
  await api.hubWhoami();
  assert.equal(requests[0].options.headers.Authorization, 'Bearer old-fictional-token');
  assert.equal(requests[1].options.headers.Authorization, 'Bearer replacement-fictional-token');
  assert.equal(api.getStoredHubToken(), 'replacement-fictional-token');
});

test('incorrect old password preserves a valid current session', async () => {
  const { api } = harness([{ status: 400, body: { detail: 'current password is incorrect' } }]);
  await assert.rejects(api.hubChangePassword('wrong', 'new'), error => error.status === 400);
  assert.equal(api.getStoredHubToken(), 'old-fictional-token');
});

test('revoked session clears storage and notifies the login gate', async () => {
  const { api } = harness([{ status: 401, body: {} }]);
  let notices = 0;
  api.setHubUnauthorizedHandler(() => notices++);
  await assert.rejects(api.hubWhoami(), error => error.status === 401);
  assert.equal(api.getStoredHubToken(), '');
  assert.equal(notices, 1);
});

test('client remains compatible with an older server without token replacement', async () => {
  const { api } = harness([{ status: 200, body: { ok: true } }]);
  await api.hubChangePassword('old', 'new');
  assert.equal(api.getStoredHubToken(), 'old-fictional-token');
});

test('a delayed old-session rejection preserves a replacement Hub session', async () => {
  const { api } = harness([{ status: 401, body: {} }]);
  let notices = 0;
  api.setHubUnauthorizedHandler(() => notices++);
  const pending = api.hubWhoami();
  api.setStoredHubToken('new-fictional-token');
  await assert.rejects(pending, error => error.status === 401);
  assert.equal(api.getStoredHubToken(), 'new-fictional-token');
  assert.equal(notices, 0);
});
