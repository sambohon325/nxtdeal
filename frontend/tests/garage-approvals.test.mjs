import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';

// Deterministic handler tests; actual browser/network behavior is checked separately.
const source = ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/MyGarageApprovals.tsx', import.meta.url), 'utf8') + '\nexport { Card, Inner };', {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick = () => new Promise(resolve => setImmediate(resolve));
const item = { ro_id: 'fixture', vehicle: 'Fixture vehicle', service_number: '1', estimate_amount: 450, estimate_status: 'approved', paid: false, concerns: [] };
function harness(submit, request = {}) {
  let states = [], cursor = 0;
  const calls = [], notices = [];
  const hook = initial => { const index = cursor++; if (!(index in states)) states[index] = initial; return [states[index], value => { states[index] = value; }]; };
  const scope = { exports: {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return { useState: hook, useRef: initial => hook({ current: initial })[0] };
    if (name === 'react/jsx-runtime') return jsx;
    if (name === './kit') return { useAsync: () => request, ListCard: ({children}) => children, EmptyNote: ({children}) => children };
    if (name === '@/components/apps/CustomerVerifyGate') return { CustomerVerifyGate: ({children}) => children };
    if (name === '@/lib/garage') return { payMyRo: async (...args) => { calls.push(args); return submit(); }, respondToApproval: async (...args) => { calls.push(args); return submit(); } };
    if (name === '@/lib/apps/registry') return { accentOf: () => ({}) };
    throw Error(`Unexpected dependency: ${name}`);
  } };
  vm.runInNewContext(source, scope);
  const render = (which = 'Card', value = item) => { cursor = 0; return scope.exports[which]({ item: value, onChanged: notice => notices.push(notice) }); };
  return { render, calls, notices, html: which => renderToStaticMarkup(render(which)) };
}

test('only one payment request; simulation is reported explicitly', async () => {
  let finish;
  const h = harness(() => new Promise(resolve => { finish = resolve; }));
  const button = elements(h.render()).find(e => e.type === 'button');
  button.props.onClick(); button.props.onClick();
  assert.equal(h.calls.length, 1);
  finish({ ok: true, mode: 'simulated' }); await tick();
  assert.match(h.notices[0], /no money was collected/);
  button.props.onClick(); assert.equal(h.calls.length, 1);
});

test('failure retains recovery without exposing processor details', async () => {
  const h = harness(async () => { throw Error('private provider detail'); });
  elements(h.render()).find(e => e.type === 'button').props.onClick(); await tick();
  assert.match(h.html(), /could not be confirmed|Refresh records/);
  assert.doesNotMatch(h.html(), /private provider detail/);
  assert.equal(h.notices.length, 0);
});

test('explicit unsuccessful response does not produce a success notice', async () => {
  const h = harness(async () => ({ ok: false, mode: 'live' }));
  elements(h.render()).find(e => e.type === 'button').props.onClick(); await tick();
  assert.equal(h.notices.length, 0);
  assert.match(h.html(), /could not be confirmed/);
});

test('fetch failure offers retry rather than claiming an empty approvals queue', () => {
  let retried = false;
  const h = harness(null, { error: 'private error', reload: () => { retried = true; } });
  assert.match(h.html('Inner'), /couldn.*load your approvals/);
  assert.doesNotMatch(h.html('Inner'), /Nothing needs|private error/);
  elements(h.render('Inner')).find(e => e.type === 'button').props.onClick();
  assert.equal(retried, true);
});

test('payment notice survives the approval disappearing after refresh', () => {
  const request = { data: { count: 1, approvals: [item] }, reload: () => {} };
  const h = harness(null, request);
  const card = elements(h.render('Inner')).find(e => typeof e.type === 'function' && e.props.item);
  card.props.onChanged('Demo payment recorded — no money was collected.');
  request.data = { count: 0, approvals: [] };
  assert.match(h.html('Inner'), /no money was collected/);
});
