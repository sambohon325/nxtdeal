import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';
const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/salesDay.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
test('sales day prioritizes overdue work, excludes completed tasks and leaves undated tasks last',()=>{
 const input=[{id:'later',due_at:'2026-10-13T10:00:00Z'},{id:'done',due_at:'2026-10-01T10:00:00Z',completed:true},{id:'undated',due_at:null},{id:'bad-date',due_at:'invalid'},{id:'overdue',due_at:'2026-10-11T10:00:00Z'}];
 const result=scope.exports.salesDayQueue(input,Date.parse('2026-10-12T10:00:00Z'));
 assert.equal(result.map(t=>t.id).join(','),'overdue,later,bad-date,undated');assert.equal(result.filter(t=>t.overdue).length,1);assert.equal(input[0].id,'later');
});

import * as jsx from 'react/jsx-runtime';
test('sales day keeps unavailable actions out of restricted roles',()=>{
 const component={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useState:v=>[v,()=>{}],useEffect:()=>{}}:name.endsWith('salesDay')?scope.exports:name.endsWith('/DepartmentOverview')?{OverviewActions:'OverviewActions'}:name.endsWith('.css')?{default:{}}:{})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/sales/SalesDay.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,component);
 const visited=[]; const tree=component.exports.SalesDay({allowed:new Set(['inventory']),revision:0,onNavigate:key=>visited.push(key)});
 const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
 const actions=walk(tree).find(e=>e.type==='OverviewActions').props.items;
 assert.equal(actions.length,1);
 assert.equal(actions[0].label,'Browse vehicles');
 actions[0].onClick();
 assert.deepEqual(visited,['inventory']);
 assert.equal(walk(tree).filter(e=>e.type==='button').length,0);
});
