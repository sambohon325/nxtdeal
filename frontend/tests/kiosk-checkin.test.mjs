import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';

// Exercise component handlers with deterministic state and API doubles. Browser
// navigation, network delivery and React scheduling need separate browser checks.
const source = ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/KioskCheckin.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const appointment = { department: 'Service', person_name: 'Private customer', vehicle: 'Car', scheduled_start: '2026-10-02T18:00:00Z', status: 'scheduled', checkin: null, revoked: false };
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness(request, submit = async () => ({ ...appointment, checkin: {} }), key = "checkin") {
  let states = [], cursor = 0;
  const calls = [];
  const hook = initial => { const index = cursor++; if (!(index in states)) states[index] = initial; return [states[index], value => { states[index] = value; }]; };
  const scope = { exports: {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return { useState: hook, useRef: initial => hook({ current: initial })[0], useEffect: () => {} };
    if (name === '@/lib/kioskPrivacy') return {};
    if (name === 'react/jsx-runtime') return jsx;
    if (name === './kit') return { useAsync: () => request };
    if (name === '@/lib/appointmentScheduling') return { publicSubmitCheckin: async (...args) => { calls.push(args); return submit(); } };
    throw Error(`Unexpected dependency: ${name}`);
  } };
  vm.runInNewContext(source, scope);
  const outer = () => { cursor = 0; return scope.exports.KioskCheckin({ screen: { heading: 'Check in', key } }); };
  elements(outer()).find(e => e.type === 'input').props.onChange({ target: { value: 'private-code' } });
  elements(outer()).find(e => e.type === 'form').props.onSubmit({ preventDefault() {} });
  const inner = elements(outer()).find(e => typeof e.type === 'function');
  states = [];
  const render = () => { cursor = 0; return inner.type(inner.props); };
  return { render, calls, html: () => renderToStaticMarkup(render()) };
}

test('closed and revoked appointments do not offer submission', () => {
  for (const status of ['completed', 'cancelled', 'no_show']) {
    const h = harness({ data: { ...appointment, status } });
    assert.doesNotMatch(h.html(), /Save check-in details/);
  }
  const h = harness({ data: { ...appointment, revoked: true } });
  assert.doesNotMatch(h.html(), /Private customer|Save check-in details/);
});

test('one in-flight submission; confirmed result removes the form', async () => {
  let finish;
  const h = harness({ data: appointment }, () => new Promise(resolve => { finish = resolve; }));
  const tree = h.render();
  const inputs = elements(tree).filter(e => e.type === 'input' || e.type === 'textarea');
  inputs[0].props.onChange({ target: { value: ' text ' } });
  inputs[1].props.onChange({ target: { value: ' oil change ' } });
  const form = elements(h.render()).find(e => e.type === 'form');
  form.props.onSubmit({ preventDefault() {} });
  form.props.onSubmit({ preventDefault() {} });
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.calls[0], ['private-code', 'wait', 'text', 'oil change']);
  finish({ ...appointment, checkin: {} }); await tick();
  assert.match(h.html(), /pre-visit details are saved/);
  assert.doesNotMatch(h.html(), /Save check-in details/);
});

test('failed submission keeps retry available without claiming success', async () => {
  const h = harness({ data: appointment }, async () => { throw Error('private server detail'); });
  elements(h.render()).find(e => e.type === 'form').props.onSubmit({ preventDefault() {} });
  await tick();
  assert.match(h.html(), /could not be confirmed|Save check-in details/);
  assert.doesNotMatch(h.html(), /private server detail|pre-visit details are saved/);
  elements(h.render()).find(e => e.type === 'form').props.onSubmit({ preventDefault() {} });
  await tick(); assert.equal(h.calls.length, 2);
});

test('lookup errors expose retry without rendering customer data', () => {
  let retried = false;
  const h = harness({ error: 'private error', data: appointment, reload: () => { retried = true; } });
  assert.doesNotMatch(h.html(), /Private customer|private error|Save check-in details/);
  elements(h.render()).find(e => e.type === 'button' && e.props.children === 'Try again').props.onClick();
  assert.equal(retried, true);
});

test('waiting view reads only its appointment and refreshes without a check-in mutation', () => {
 let refreshes=0; const request={data:{...appointment,status:'confirmed',checkin:{}},reload:()=>{refreshes++;}};
 const h=harness(request,async()=>{throw Error('Must not submit');},'queue');
 assert.match(h.html(),/Appointment status: confirmed/);
 assert.match(h.html(),/Queue position and wait estimates are not available/);
 assert.doesNotMatch(h.html(),/Save check-in details|<form|<input/);
 elements(h.render()).find(e=>e.type==='button'&&e.props.children==='Refresh appointment status').props.onClick();
 assert.equal(refreshes,1);assert.equal(h.calls.length,0);
 request.error='revoked';assert.doesNotMatch(h.html(),/Private customer|Appointment status:/);
});

test('shared kiosk expiry removes appointment and code; warning can extend display', () => {
  const states = []; let cursor = 0, effect, lastToken, cleanup, warn, expire, restarts = 0, stops = 0;
  const hook = initial => { const i = cursor++; if (!(i in states)) states[i] = initial; return [states[i], value => {states[i] = value;}]; };
  const scope = {exports:{}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return {useState:hook, useRef: initial => hook({current:initial})[0], useEffect:(fn,deps) => { if(deps[0] !== lastToken){lastToken=deps[0];effect=fn;} }};
    if (name === 'react/jsx-runtime') return jsx;
    if (name === './kit') return {};
    if (name === '@/lib/appointmentScheduling') return {};
    if (name === '@/lib/kioskPrivacy') return {startKioskPrivacyTimer:(w,e) => {warn=w;expire=e;return {restart:()=>{restarts++;w(false);},stop:()=>stops++};}};
    throw Error(name);
  }};
  vm.runInNewContext(source,scope);
  const render = () => {cursor=0;const tree=scope.exports.KioskCheckin({screen:{heading:'Check in',key:'checkin'}});if(effect){cleanup?.();cleanup=effect();effect=null;}return tree;};
  elements(render()).find(e=>e.type==='input').props.onChange({target:{value:'private-code'}});
  elements(render()).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
  assert.ok(elements(render()).some(e=>typeof e.type==='function'));
  warn(true);
  elements(render()).find(e=>e.type==='button'&&e.props.children==='Keep my details on screen').props.onClick();
  assert.equal(restarts,1);
  expire();const cleared=render();
  assert.equal(elements(cleared).some(e=>typeof e.type==='function'),false);
  assert.equal(elements(cleared).find(e=>e.type==='input').props.value,'');
  assert.equal(stops,1);
  assert.doesNotMatch(renderToStaticMarkup(cleared),/private-code|Keep my details on screen/);
});
