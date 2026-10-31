import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const walk=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(walk)];
test('dispatch selection requires an explicit save and preserves the current repair order',async()=>{
 const board={unassigned:[{id:'SYN',service_number:'RO-SYN',description:'Fictional concern',ro_stage:'RO Written'}],technicians:{TECH:{name:'Fictional Tech',repair_orders:[]}}};
 const states=[board,{},'',false,0,false];let cursor=0,role='SERVICE';const calls=[];
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];}}:name==='@/lib/auth'?{getSession:()=>({role})}:name==='@/lib/shopControl'?{assignTechnician:async(...args)=>calls.push(args)}:name.endsWith('.css')?{default:{}}:{})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/DispatchDay.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{cursor=0;return walk(scope.exports.DispatchDay({theme:'dark'}));};let tree=render();assert.equal(tree.find(e=>e.props.children==='Save assignment').props.disabled,true);
 tree.filter(e=>e.type==='select').at(-1).props.onChange({target:{value:'TECH'}});assert.equal(calls.length,0);
 tree=render();await tree.find(e=>e.props.children==='Save assignment').props.onClick();assert.deepEqual(calls,[['SYN','TECH']]);
 role='SALES';assert.ok(!render().some(e=>e.props.children==='Save assignment'));
});
