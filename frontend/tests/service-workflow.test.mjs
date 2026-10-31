import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';

const source = ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/ServiceRoBoard.tsx', import.meta.url), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX},
}).outputText;
const elements = e => !e || typeof e !== 'object' ? [] : [e, ...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness() {
  let states = [], cursor = 0;
  const board = {
    Repair: [{id:'SYN-A', service_number:'1001', vin:'SYN-VIN-A', description:'Oil service', technician:'Alex'}],
    Parts: [{id:'SYN-B', service_number:'1002', vin:'SYN-VIN-B', description:'Brake repair', technician:'Blair'}],
  };
  const scope = {exports:{}, require: name => {if(name.endsWith('/WorkspaceUi'))return workControls;
    if (name === 'react') return {useState: initial => {const i = cursor++; if (!(i in states)) states[i] = initial; return [states[i], value => {states[i] = value;}];}};
    if (name === 'react/jsx-runtime') return jsx;
    if (name === '@/lib/repairOrders') return {};
    if (name === '@/components/RepairOrderWorkspaceBoard') return {RoWorkspaceModal:'modal'};
    if (name === './kit') return {useAsync: () => ({data:board,loading:false,error:null,reload:()=>{}}),
      WiredScreen:'frame', StatGrid:'stats', ListCard:'list', Row:'row', EmptyNote:'empty'};
    throw Error(name);
  }};
  vm.runInNewContext(source,scope);
  const render = () => {cursor=0; return elements(scope.exports.ServiceRoBoard({app:{},screen:{}}));};
  return {render};
}
test('service search combines stage and record details without changing totals', () => {
  const h = harness();
  let tree = h.render();
  assert.equal(tree.filter(e=>e.type==='row').length,2);
  tree.find(e=>e.type==='input').props.onChange({target:{value:'syn-vin-b'}});
  tree = h.render();
  assert.match(tree.find(e=>e.type==='row').props.primary,/1002/);
  assert.equal(tree.find(e=>e.type==='stats').props.stats[0].value,2);
  tree.find(e=>e.type==='select').props.onChange({target:{value:'Repair'}});
  tree = h.render();
  assert.equal(tree.filter(e=>e.type==='row').length,0);
  assert.ok(tree.some(e=>e.props?.role==='status'));
  tree.find(e=>e.type==='button').props.onClick();
  assert.equal(h.render().filter(e=>e.type==='row').length,2);
});
test('opening and returning from an order preserves the selected stage and search', () => {
  const h = harness();
  let tree = h.render();
  tree.find(e=>e.type==='input').props.onChange({target:{value:'Brake'}});
  tree.find(e=>e.type==='select').props.onChange({target:{value:'Parts'}});
  tree = h.render();
  tree.find(e=>e.type==='row').props.onClick();
  tree = h.render();
  const detail = tree.find(e=>e.props?.roId==='SYN-B');
  assert.ok(detail);
  detail.props.onClose();
  tree = h.render();
  assert.equal(tree.find(e=>e.type==='input').props.value,'Brake');
  assert.equal(tree.find(e=>e.type==='select').props.value,'Parts');
  assert.equal(tree.filter(e=>e.type==='row').length,1);
  assert.ok(!tree.some(e=>e.props?.roId));
});
