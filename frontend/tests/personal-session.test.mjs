import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function harness() {
  let token = '', complete;
  const events = [], requests = [];
  const scope = {
    exports: {}, Event,
    sessionStorage: { getItem: () => token, setItem: (_, value) => { token = value; }, removeItem: () => { token = ''; } },
    window: { dispatchEvent: event => events.push(event.type) },
    fetch: (url, options) => { requests.push({ url, options }); return new Promise(resolve => { complete = resolve; }); },
    require: name => {
      if (name === './hubApi') return { HUB_API_BASE: 'http://127.0.0.1:9317' };
      throw Error(name);
    },
  };
  const source = ts.transpileModule(fs.readFileSync(new URL('../lib/mysalesPersonal.ts', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, scope);
  return { api: scope.exports, events, requests,
    finish: (status, data = { detail: 'Expired fictional session' }) => complete({ ok: status === 200, status, json: async () => data }) };
}

test('late 401 from an older session cannot clear a newer personal login', async () => {
  const h = harness();
  h.api.setPersonalToken('fictional-old');
  const pending = h.api.personalRequest('/records/contacts');
  h.api.setPersonalToken('fictional-new');
  h.finish(401);
  await assert.rejects(pending, /Expired fictional session/);
  assert.equal(h.api.personalToken(), 'fictional-new');
  assert.deepEqual(h.events, []);
  assert.equal(h.requests[0].options.headers.Authorization, 'Bearer fictional-old');
  assert.equal(h.requests[0].options.credentials, 'omit');
});

test('401 for the current personal session clears it and notifies the workspace', async () => {
  const h = harness();
  h.api.setPersonalToken('fictional-current');
  const pending = h.api.personalRequest('/me');
  h.finish(401);
  await assert.rejects(pending);
  assert.equal(h.api.personalToken(), '');
  assert.deepEqual(h.events, ['mysales-session-expired']);
});

test('an anonymous failed request cannot clear a subsequent login', async () => {
  const h = harness();
  const pending = h.api.personalRequest('/me');
  h.api.setPersonalToken('fictional-new');
  h.finish(401);
  await assert.rejects(pending);
  assert.equal(h.api.personalToken(), 'fictional-new');
  assert.deepEqual(h.events, []);
  assert.equal(h.requests[0].options.headers.Authorization, undefined);
});

test('permission failure preserves a valid personal session', async () => {
  const h = harness();
  h.api.setPersonalToken('fictional-current');
  const pending = h.api.personalRequest('/me');
  h.finish(403, { detail: 'Not allowed' });
  await assert.rejects(pending, /Not allowed/);
  assert.equal(h.api.personalToken(), 'fictional-current');
  assert.deepEqual(h.events, []);
});
