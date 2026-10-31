import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import {WorkField} from './work-field-loader.mjs';

const source = ts.transpileModule(fs.readFileSync(new URL('../components/CustomerCommsPanel.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(send) {
  let states = [], cursor = 0, effect, cleanup, session = { mode: 'text', customerId: 'first', name: 'First' };
  const calls = [];
  const hook = initial => {
    const i = cursor++;
    if (!(i in states)) states[i] = initial;
    return [states[i], value => { states[i] = typeof value === 'function' ? value(states[i]) : value; }];
  };
  const scope = { exports: {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react/jsx-runtime') return jsx;
    if (name === './WorkField') return {WorkField};
    if (name === 'react') return { useState: hook, useRef: initial => hook({ current: initial })[0], useEffect: fn => { effect = fn; } };
    if (name === '@/lib/customerComms') return { sendText: input => { calls.push(input); return send(); } };
    if (name.startsWith('@/') || name === 'next/link') return {};
    throw Error(name);
  } };
  vm.runInNewContext(source, scope);
  const render = () => { cursor = 0; return scope.exports.CommsWorkspaceModal({ session, onClose() {} }); };
  const changeSession = next => { cleanup?.(); session = next; render(); cleanup = effect(); };
  changeSession(session);
  return {
    render, calls, changeSession,
    input: () => elements(render()).find(e => e.type === 'input'),
    send: () => elements(render()).find(e => e.type === 'button' && e.props.children === 'Send').props.onClick(),
    html: () => renderToStaticMarkup(render()),
  };
}

test('failed send retains draft, suppresses duplicate requests and exposes retry guidance', async () => {
  let reject;
  const h = harness(() => new Promise((_, r) => { reject = r; }));
  h.input().props.onChange({ target: { value: 'Keep this draft' } });
  const pending = h.send(); await h.send();
  assert.equal(h.calls.length, 1);
  assert.equal(h.input().props.disabled, true);
  reject(Error('private error')); await pending;
  assert.equal(h.input().props.value, 'Keep this draft');
  assert.match(h.html(), /role="alert"|Check recent activity/);
  assert.doesNotMatch(h.html(), /private error/);
  assert.equal(h.input().props.disabled, false);
});

test('confirmed submission clears draft and keeps message', async () => {
  const h = harness(async () => ({ communication: {} }));
  h.input().props.onChange({ target: { value: 'Hello customer' } });
  await h.send();
  assert.equal(h.input().props.value, '');
  assert.match(h.html(), /Hello customer/);
});

test('late completion cannot leak messages into another customer session', async () => {
  let finish;
  const h = harness(() => new Promise(resolve => { finish = resolve; }));
  h.input().props.onChange({ target: { value: 'First private message' } });
  const pending = h.send();
  h.changeSession({ mode: 'text', customerId: 'second', name: 'Second' });
  h.input().props.onChange({ target: { value: 'Second draft' } });
  finish({ communication: {} }); await pending;
  assert.equal(h.input().props.value, 'Second draft');
  assert.doesNotMatch(h.html(), /First private message/);
  assert.equal(h.calls[0].customer_id, 'first');
});


for (const simulated of [true, false]) {
  test(`message delivery remains honest (simulated=${simulated})`, async () => {
    const h = harness(async () => ({ communication: {}, dispatch: { simulated }, provider: { live: true } }));
    h.input().props.onChange({ target: { value: 'Delivery test' } });
    await h.send();
    assert.match(h.html(), simulated ? /Demo only.*no SMS sent/ : /Recorded.*delivery not confirmed/);
  });
}

test('dispatch-level failure retains the draft without claiming delivery', async () => {
  const h = harness(async () => ({ communication: {}, dispatch: { error: 'private adapter detail' } }));
  h.input().props.onChange({ target: { value: 'Retain on dispatch error' } });
  await h.send();
  assert.equal(h.input().props.value, 'Retain on dispatch error');
  assert.match(h.html(), /dispatch reported a problem/);
  assert.doesNotMatch(h.html(), /private adapter detail/);
});

test('search failure differs from no matches; clearing query ignores a late response', async () => {
  let states = [], cursor = 0, effects = [], timer, finish;
  const hook = initial => {
    const i = cursor++; if (!(i in states)) states[i] = initial;
    return [states[i], value => { states[i] = typeof value === 'function' ? value(states[i]) : value; }];
  };
  const scope = { exports: {}, setTimeout: fn => { timer = fn; return 1; }, clearTimeout() {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react/jsx-runtime') return jsx;
    if (name === './WorkField') return {WorkField};
    if (name === 'react') return { useState: hook, useEffect: fn => effects.push(fn) };
    if (name === '@/lib/commsStore') return { useCommsSession: () => null };
    if (name === '@/lib/customerComms') return { searchCustomers: () => new Promise((resolve, reject) => { finish = { resolve, reject }; }), fetchRecent: async () => { throw Error('private recent error'); } };
    if (name.startsWith('@/') || name === 'next/link') return {};
    throw Error(name);
  } };
  vm.runInNewContext(source, scope);
  const render = () => { cursor = 0; effects = []; return scope.exports.CustomerCommsPanel(); };
  const html = () => renderToStaticMarkup(render());
  const input = () => elements(render()).find(e => e.props?.['aria-label'] === 'Search customers to call or text');
  input().props.onChange({ target: { value: 'Sam' } }); render();
  let cleanup = effects[2](); timer(); finish.reject(Error('private search error'));
  await new Promise(resolve => setImmediate(resolve));
  assert.match(html(), /Customer search is unavailable/); assert.doesNotMatch(html(), /No customers match|private search error/);
  const retry = elements(render()).find(e => e.type === 'button' && e.props.children === 'Retry search');
  retry.props.onClick(); cleanup(); render(); cleanup = effects[2](); timer();
  input().props.onChange({ target: { value: '' } }); cleanup(); render(); effects[2]();
  finish.resolve({ results: [{ id: 'stale', name: 'Stale private customer' }] });
  await new Promise(resolve => setImmediate(resolve));
  assert.doesNotMatch(html(), /Searching|Stale private customer|Customer search is unavailable/);
  render(); effects[1](); await new Promise(resolve => setImmediate(resolve));
  assert.match(html(), /Recent conversations are unavailable/); assert.doesNotMatch(html(), /private recent error/);
});
