import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/ParentWebsitePicker.tsx',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
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
 if(name==='@/lib/websites')return api;
 throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;ec=0;const tree=scope.exports.ParentWebsitePicker(props);while(pending.length)pending.shift()();return tree;};
 return{render,find:type=>elements(render()).find(e=>e.type===type)};
}


const button=(h,label)=>elements(h.render()).find(e=>e.type==='button'&&e.props.children===label);
test('missing current choice is preserved and unlink requires confirmation',async()=>{
 let applied='unchanged';const h=harness({listMyWebsites:async()=>[]},{current:'OLD',disabled:false,onApply:async id=>applied=id});h.render();await tick();
 assert.equal(h.find('select').props.value,'OLD');assert.match(JSON.stringify(h.render()),/Current linked website/);
 h.find('select').props.onChange({target:{value:''}});button(h,'Apply branding source').props.onClick();assert.equal(applied,'unchanged');
 button(h,'Cancel branding change').props.onClick();assert.equal(applied,'unchanged');button(h,'Apply branding source').props.onClick();await button(h,'Confirm branding change').props.onClick();assert.equal(applied,null);
});
test('failed list hides choices and retries without changing the parent',async()=>{
 let calls=0;const h=harness({listMyWebsites:async()=>{if(++calls===1)throw Error('secret');return[{id:'SITE1',name:'My site'}];}},{current:null,disabled:false,onApply:async()=>{throw Error('unexpected');}});h.render();await tick();
 assert.equal(h.find('select'),undefined);assert.doesNotMatch(JSON.stringify(h.render()),/secret/);button(h,'Retry websites').props.onClick();h.render();await tick();assert.match(JSON.stringify(h.render()),/My site/);
});
