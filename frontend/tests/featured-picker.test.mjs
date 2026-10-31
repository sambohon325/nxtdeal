import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/FeaturedVehiclePicker.tsx',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(api, props){
 const state=[], effects=[],pending=[];let cursor=0,ec=0;
 const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}];};
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
 if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0],useEffect:(fn,deps)=>{const i=ec++;if(!effects[i]||deps.some((v,j)=>v!==effects[i][j])){effects[i]=deps;pending.push(fn);}}};
 if(name==='react/jsx-runtime')return jsx;
 if(name==='./kit')return {WiredScreen:'frame'};
 if(name==='./FeaturedVehiclePicker')return {FeaturedVehiclePicker:'picker'};
 if(name==='@/components/PersonalPage')return {PersonalPage:'preview'};
 if(name==='@/lib/inventoryWorkspace')return {normalizeListItem:v=>v,...api};
 throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;ec=0;const tree=scope.exports.FeaturedVehiclePicker(props);while(pending.length)pending.shift()();return tree;};
 return{render,find:type=>elements(render()).find(e=>e.type===type)};
}

const vehicles=[{id:'V1',title:'Toyota Camry',subtitle:'Stock 1',vin:'VIN1'},{id:'V2',title:'Honda Civic',subtitle:'Stock 2',vin:'VIN2'}];
test('load failure preserves selection and retry recovers choices',async()=>{
 let calls=0;const props={selected:['V1'],disabled:false,onChange(){throw Error('should not change');}};
 const h=harness({getInventorySummary:async()=>{if(++calls===1)throw Error('private');return{vehicles};}},props);
 h.render();await tick();assert.match(JSON.stringify(h.render()),/unchanged/);assert.doesNotMatch(JSON.stringify(h.render()),/private/);
 elements(h.render()).find(e=>e.type==='button'&&e.props.children==='Retry inventory').props.onClick();h.render();await tick();assert.match(JSON.stringify(h.render()),/Toyota Camry/);
});
test('search does not discard selection and removing unavailable IDs is possible',async()=>{
 let next;const props={selected:['V1','removed'],disabled:false,onChange:ids=>next=ids};
 const h=harness({getInventorySummary:async()=>({vehicles})},props);h.render();await tick();
 h.find('input').props.onChange({target:{value:'Honda'}});const checks=elements(h.render()).filter(e=>e.type==='input'&&e.props.type==='checkbox');assert.equal(checks.length,1);
 checks[0].props.onChange({target:{checked:true}});assert.deepEqual([...next],['V1','removed','V2']);
 elements(h.render()).find(e=>e.props?.['aria-label']==='Remove removed').props.onClick();assert.deepEqual([...next],['V1']);
});
test('limit blocks additional selections but allows removal',async()=>{
 const props={selected:Array.from({length:24},(_,i)=>'V'+i),disabled:false,onChange(){}};
 const h=harness({getInventorySummary:async()=>({vehicles:[...vehicles,{id:'new',title:'New',subtitle:''}]})},props);h.render();await tick();
 const checks=elements(h.render()).filter(e=>e.type==='input'&&e.props.type==='checkbox');assert.equal(checks[0].props.disabled,false);assert.equal(checks[2].props.disabled,true);
});

