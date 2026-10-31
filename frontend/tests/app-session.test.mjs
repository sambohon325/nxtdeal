import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function harness() {
  const data = new Map();
  const listeners = new Set();
  const localStorage = {
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: key => data.delete(key),
  };
  let mirrored = null;
  const scope = {
    exports: {}, process: { env: {} }, localStorage,
    window: { localStorage, addEventListener: (_, fn) => listeners.add(fn), removeEventListener: (_, fn) => listeners.delete(fn) },
    require: name => {
      if (name === './canonicalApiUrl') return { canonicalApiUrl: value => value };
      if (name === '@/lib/api') return { API_BASE: 'http://127.0.0.1:8317' };
      if (name === '@/lib/hubApi') return { HUB_API_BASE: 'http://127.0.0.1:9317' };
      if (name === '@/lib/auth') return { getSession: () => mirrored };
      throw Error(name);
    },
  };
  const source = ts.transpileModule(fs.readFileSync(new URL('../lib/appAuth.ts', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, scope);
  return { api: scope.exports, mirror: value => { mirrored = value; },
    event: event => listeners.forEach(fn => fn({ storageArea: localStorage, ...event })),
    listenerCount: () => listeners.size };
}

test('other-tab logout, account replacement, tenant switch and clear invalidate the app view', () => {
  for (const key of ['dealeros_app_session', 'dealeros_session', 'dealeros_tenant_api', null]) {
    const h = harness(); let changes = 0;
    const unsubscribe = h.api.subscribeAppSessionChange(() => changes++);
    h.event({ key, oldValue: 'old', newValue: null });
    assert.equal(changes, 1, key);
    h.event({ key, oldValue: 'old', newValue: 'new' });
    assert.equal(changes, 2, key);
    unsubscribe();
    assert.equal(h.listenerCount(), 0);
    h.event({ key, oldValue: 'new', newValue: null });
    assert.equal(changes, 2);
  }
});

test('unrelated appearance and sessionStorage changes do not interrupt work', () => {
  const h = harness(); let changes = 0;
  h.api.subscribeAppSessionChange(() => changes++);
  h.event({ key: 'appearance', oldValue: 'dark', newValue: 'light' });
  h.event({ key: 'dealeros_session', oldValue: 'same', newValue: 'same' });
  h.event({ key: 'dealeros_session', oldValue: 'old', newValue: null, storageArea: {} });
  assert.equal(changes, 0);
});

test('an app identity cannot survive missing or replaced mirrored staff credentials', () => {
  const h = harness();
  const session = { token: 'fictional-token', employeeId: 'SYN-1', dealershipId: 'synthetic', role: 'SERVICE' };
  h.api.saveAppSession(session);
  assert.equal(h.api.getAppSession(), null);
  h.mirror({ ...session, token: 'other-fictional-token' });
  assert.equal(h.api.getAppSession(), null);
  h.mirror({ ...session, employeeId: 'SYN-2' });
  assert.equal(h.api.getAppSession(), null);
  h.mirror(session);
  assert.equal(h.api.getAppSession().employeeId, 'SYN-1');
  h.api.clearAppSession();
  assert.equal(h.api.getAppSession(), null);
});
