import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../lib/appAuth.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const response = (body, ok = true) => ({ ok, json: async () => body });

function harness(login) {
  const data = new Map([['dealeros_tenant_api', 'https://old.example.test']]);
  const writes = [], requests = [];
  let mirrored = { token: 'old-fictional-token', employeeId: 'OLD' };
  const scope = {
    exports: {}, window: {}, process: { env: { NEXT_PUBLIC_DEPLOYMENT_MODE: 'apps' } },
    localStorage: {
      getItem: key => data.get(key) ?? null,
      setItem: (key, value) => { writes.push(key); data.set(key, value); },
    },
    require: name => {
      if (name === './canonicalApiUrl') return { canonicalApiUrl: value => value };
      if (name === '@/lib/api') return {
        API_BASE: 'https://old.example.test',
        setTenantApiBase: value => { writes.push('tenant'); data.set('dealeros_tenant_api', value); },
        clearTenantApiBase: () => { writes.push('clear-tenant'); data.delete('dealeros_tenant_api'); },
      };
      if (name === '@/lib/hubApi') return { HUB_API_BASE: 'https://hub.example.test' };
      if (name === '@/lib/auth') return { getSession: () => mirrored, saveSession: value => { writes.push('staff'); mirrored = value; } };
      throw Error(name);
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (requests.length === 1) return response({ api_base_url: 'https://new.example.test', name: 'Fictional New Store', dealer_id: 'NEW' });
      return login();
    },
  };
  vm.runInNewContext(source, scope);
  return { api: scope.exports, data, writes, requests, mirrored: () => mirrored };
}

test('pending tenant login does not switch routing or credentials in existing tabs', async () => {
  let finish;
  const h = harness(() => new Promise(resolve => { finish = resolve; }));
  const pending = h.api.appLogin('new-store', 'NEW-EMP', 'fictional-only');
  while (!finish) await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(h.writes, []);
  assert.equal(h.data.get('dealeros_tenant_api'), 'https://old.example.test');
  finish(response({ token: 'new-fictional-token', employee_id: 'NEW-EMP', role: 'SALES' }));
  const result = await pending;
  assert.equal(result.ok, true);
  assert.equal(result.reload, true);
  assert.equal(h.data.get('dealeros_tenant_api'), 'https://new.example.test');
  assert.equal(h.api.getAppSession().token, h.mirrored().token);
  assert.equal(h.mirrored().apiBaseUrl, 'https://new.example.test');
  assert.equal(h.requests[1].url, 'https://new.example.test/auth/login');
  assert.equal(h.requests[1].options.headers.Authorization, undefined);
});

for (const [name, login] of [
  ['invalid credentials', () => response({ error: 'Invalid credentials' })],
  ['HTTP rejection with a token-shaped body', () => response({ token: 'not-a-valid-login' }, false)],
  ['missing token', () => response({})],
  ['empty token', () => response({ token: '  ' })],
  ['non-string token', () => response({ token: { malformed: true } })],
  ['network failure', () => { throw Error('Fictional network failure'); }],
]) test(`failed tenant switch preserves the existing session: ${name}`, async () => {
  const h = harness(login);
  const result = await h.api.appLogin('new-store', 'NEW-EMP', 'fictional-only');
  assert.equal(result.ok, false);
  assert.deepEqual(h.writes, []);
  assert.equal(h.data.get('dealeros_tenant_api'), 'https://old.example.test');
  assert.equal(h.mirrored().token, 'old-fictional-token');
});
