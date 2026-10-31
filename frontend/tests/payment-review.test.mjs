import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../components/PaymentReviewPanel.tsx', import.meta.url), 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const nativeJsx = {jsx:(type,props)=>typeof type==='function'?type(props):({type,props}),jsxs:(type,props)=>typeof type==='function'?type(props):({type,props})};
const paginationScope={exports:{},require:()=>nativeJsx};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/CollectionPagination.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,paginationScope);
function harness() {
  const states = [], effects = [], requests = []; let cursor = 0;
  const scope = {exports: {}, AbortController, require: name => name.endsWith('/CollectionPagination')?paginationScope.exports:name.endsWith('/WorkspaceUi')?workControls:(name === 'react' ? {
    useEffect: fn => effects.push(fn),
    useState: initial => {const i = cursor++; if (!(i in states)) states[i] = initial;
      return [states[i], value => {states[i] = typeof value === 'function' ? value(states[i]) : value;}];},
  } : name === 'react/jsx-runtime' ? nativeJsx : {
    getPaymentReview: (offset, signal) => new Promise((resolve, reject) => requests.push({offset, signal, resolve, reject})),
    paymentReviewReasons: {},
  })};
  vm.runInNewContext(source, scope);
  return {requests, states, render: () => {cursor = 0; effects.length = 0; return scope.exports.PaymentReviewPanel();}, start: () => effects[0]()};
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const report = {scanned_payments: 26, flagged_payments: 26, flagged_approved_receipt_total: '123.45', records: [], has_more: true};
function find(tree, predicate) {
  if (!tree) return null;
  if (Array.isArray(tree)) {for (const child of tree) {const found = find(child, predicate); if (found) return found;} return null;}
  return predicate(tree) ? tree : find(tree.props?.children, predicate);
}
const button = (tree, text) => find(tree, item => item.type === 'button' && item.props.children === text);

test('superseded response is ignored and the next page hides the previous result', async () => {
  const h = harness(); h.render(); const cancel = h.start(); cancel();
  h.requests[0].resolve(report); await settle(); assert.equal(h.states[2], null);
  h.render(); h.start(); h.requests[1].resolve(report); await settle();
  button(h.render(), 'Next').props.onClick();
  const loading = h.render(); assert.ok(find(loading, item => item.props?.role === 'status'));
  assert.equal(find(loading, item => item.type === 'dl'), null);
  h.start(); assert.equal(h.requests[2].offset, 25);
});

test('failed request exposes retry without suggesting a clean review', async () => {
  const h = harness(); h.render(); h.start(); h.requests[0].reject(new Error('Access denied')); await settle();
  const failed = h.render(); assert.ok(find(failed, item => item.props?.role === 'alert'));
  assert.equal(find(failed, item => item.type === 'dl'), null);
  button(failed, 'Try again').props.onClick(); h.render(); h.start();
  h.requests[1].resolve({...report, flagged_payments: 0, has_more: false}); await settle();
  const recovered = h.render(); assert.equal(button(recovered, 'Next').props.disabled, true);
  assert.ok(find(recovered, item => typeof item.props?.children === 'string' && item.props.children.includes('does not confirm bank reconciliation')));
});

test('refresh returns to the first page and a cancelled failure is ignored', async () => {
  const h = harness(); h.render(); h.start(); h.requests[0].resolve(report); await settle();
  button(h.render(), 'Next').props.onClick(); h.render(); const cancel = h.start(); cancel();
  h.requests[1].reject(new Error('Old failure')); await settle();
  assert.equal(h.states[2].error, undefined);
  h.render(); h.start(); h.requests[2].resolve({...report, has_more: false}); await settle();
  button(h.render(), 'Refresh review').props.onClick(); h.render(); h.start();
  assert.equal(h.requests[3].offset, 0);
});
