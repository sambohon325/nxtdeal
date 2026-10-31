import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source = ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/ReceptionAway.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(save) {
  const state = [], calls = [];
  let cursor = 0;
  const hook = initial => {
    const i = cursor++;
    if (!(i in state)) state[i] = initial;
    return [state[i], value => { state[i] = value; }];
  };
  const scope = { exports: {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return { useState: hook, useRef: v => hook({ current: v })[0], useEffect: () => {} };
    if (name === 'react/jsx-runtime') return jsx;
    if (name === '@/lib/apps/appTheme') return { useAppTheme: () => ({ dealershipName: 'Fixture' }) };
    if (name === '@/lib/upSystem') return { logUp: async input => { calls.push(input); return save(input); } };
    throw Error(name);
  } };
  vm.runInNewContext(source, scope);
  const render = () => { cursor = 0; return scope.exports.ReceptionAway({ app: {}, screen: {} }); };
  const fill = (label, value) => elements(render()).find(e => e.props?.['aria-label'] === label).props.onChange({ target: { value } });
  return { render, fill, calls };
}
const event = { preventDefault() {} };
test('walk-in submission is single-flight and confirms recorded assignment without notification promise', async () => {
  let resolve;
  const h = harness(() => new Promise(r => { resolve = r; }));
  h.fill('Your name', ' Fixture Visitor ');
  const submit = elements(h.render()).find(e => e.type === 'form').props.onSubmit;
  const pending = submit(event);
  await submit(event);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].first_name, 'Fixture Visitor');
  assert.ok(elements(h.render()).filter(e => e.type === 'input').every(e => e.props.disabled));
  resolve({ first_name: 'Fixture Visitor', assigned_to_name: 'Fixture Rep' });
  await pending;
  const tree = h.render();
  assert.match(JSON.stringify(tree), /recorded and assigned to Fixture Rep/);
  assert.doesNotMatch(JSON.stringify(tree), /notified|will be right/);
  elements(tree).find(e => e.type === 'button').props.onClick();
  assert.equal(elements(h.render()).find(e => e.props?.['aria-label'] === 'Your name').props.value, '');
});
test('failed walk-in keeps the draft and offers safe staff verification', async () => {
  const h = harness(async () => { throw Error('private backend details'); });
  h.fill('Your name', 'Fixture Visitor');
  h.fill('Phone number (optional)', '5550100');
  await elements(h.render()).find(e => e.type === 'form').props.onSubmit(event);
  const tree = h.render();
  assert.match(JSON.stringify(elements(tree).find(e => e.props?.role === 'alert')), /front desk to check/);
  assert.doesNotMatch(JSON.stringify(tree), /private backend/);
  assert.equal(elements(tree).find(e => e.props?.['aria-label'] === 'Phone number (optional)').props.value, '5550100');
});
