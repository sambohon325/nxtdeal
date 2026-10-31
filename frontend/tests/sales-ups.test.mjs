import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source = ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/SalesUps.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(save, listError = null) {
  const state = [], calls = [];
  let cursor = 0, asyncIndex = 0, reloads = 0;
  const hook = initial => {
    const i = cursor++;
    if (!(i in state)) state[i] = initial;
    return [state[i], value => { state[i] = value; }];
  };
  const scope = { exports: {}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return { useState: hook, useRef: v => hook({ current: v })[0] };
    if (name === 'react/jsx-runtime') return jsx;
    if (name === '@/lib/apps/registry') return { accentOf: () => ({}) };
    if (name === './kit') return {useAsync: () => ({loading:false, data:asyncIndex++ === 0 ? {} : [], error:asyncIndex === 2 ? listError : null,reload:()=>{reloads++;}})};
    if (name === '@/lib/upSystem') return { logUp: async input => { calls.push(input); return save(input); } };
    throw Error(name);
  } };
  vm.runInNewContext(source, scope);
  const render = () => { cursor = 0; asyncIndex = 0; return scope.exports.SalesUps({ app: {}, screen: {} }); };
  const fill = (label, value) => elements(render()).find(e => e.props?.['aria-label'] === label).props.onChange({ target: { value } });
  return { render, fill, calls, reloads:()=>reloads };
}
const event = { preventDefault() {} };
test('walk-in rejects duplicate pending saves and clears only on success', async () => {
  let resolve;
  const h=harness(()=>new Promise(r=>{resolve=r;}));h.fill('Customer first name','Fixture');
  const submit=elements(h.render()).find(e=>e.type==='form').props.onSubmit;
  const pending=submit(event);await submit(event);assert.equal(h.calls.length,1);
  assert.ok(elements(h.render()).filter(e=>e.type==='input').every(e=>e.props.disabled));
  resolve({});await pending;
  assert.equal(elements(h.render()).find(e=>e.props?.['aria-label']==='Customer first name').props.value,'');
  assert.equal(h.reloads(),2);
});
test('failed walk-in keeps draft and allows list verification without raw error',async()=>{
  const h=harness(async()=>{throw Error('private details');});h.fill('Customer first name','Fixture');h.fill('Notes (optional)','Fixture notes');
  await elements(h.render()).find(e=>e.type==='form').props.onSubmit(event);
  const tree=h.render();assert.match(JSON.stringify(tree),/could not be confirmed/);assert.doesNotMatch(JSON.stringify(tree),/private details/);
  assert.equal(elements(tree).find(e=>e.props?.['aria-label']==='Notes (optional)').props.value,'Fixture notes');
  elements(tree).find(e=>e.props?.children==='Refresh visitor list').props.onClick();assert.equal(h.reloads(),2);
});
test('list failures reach the recoverable screen instead of claiming no ups',()=>{
  const h=harness(()=>{},'fixture list unavailable');const tree=h.render();assert.equal(tree.props.error,'fixture list unavailable');tree.props.onRetry();assert.equal(h.reloads(),2);
});
