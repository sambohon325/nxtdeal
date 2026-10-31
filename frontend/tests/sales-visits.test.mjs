import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/AppointmentsBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function render(appointments,error=false){let index=0;const opened=[];const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useEffect:()=>{},useState:initial=>{const i=index++;return [i===0?appointments:i===4?false:i===12?error:initial,()=>{}];}}:name.endsWith('.css')?{default:{}}:{})};vm.runInNewContext(source,scope);return {root:scope.exports.AppointmentsBoard({theme:'dark',workflow:true,onOpenCustomer:(...args)=>opened.push(args)}),opened};}
const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
test('visit workflow pages records without dropping them and opens the linked lead',()=>{
 const rows=Array.from({length:26},(_,i)=>({id:`a${i}`,assigned_to:'rep',lead_id:`lead${i}`,status:'confirmed',scheduled_start:`2026-10-12T1${i}:00:00Z`,notes:''}));
 const {root,opened}=render(rows);const nodes=walk(root);assert.equal(nodes.filter(n=>n.type==='article').length,25);
 assert.ok(nodes.some(n=>n.props.label==='Visits'&&n.props.total===26));
 nodes.find(n=>n.type==='button'&&n.props.children==='Open customer record →').props.onClick();assert.deepEqual(opened,[['lead0','Lead']]);
});
test('schedule failure shows retry rather than an empty schedule',()=>{
 const nodes=walk(render([],true).root);assert.ok(nodes.some(n=>n.props?.role==='alert'));assert.ok(nodes.some(n=>n.type==='button'&&n.props.children==='Retry schedule'));assert.ok(!nodes.some(n=>n.type==='h4'&&n.props.children==='No visits in this view.'));
});
