import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/ReceptionDesk.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(save, api){
 let state=[],cursor=0,effectCursor=0;const calls=[],effects=[],pending=[];
 const effect=(fn,deps)=>{if(!api)return;const i=effectCursor++;const old=effects[i];if(!old||deps.some((v,j)=>v!==old.deps[j])){old?.cleanup?.();effects[i]={deps};pending.push(()=>{effects[i].cleanup=fn()})}};
 const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return [state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}];};
 const scope={exports:{},setTimeout,clearTimeout,require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react')return {useState:hook,useRef:v=>hook({current:v})[0],useEffect:effect};
  if(name==='react/jsx-runtime')return jsx;
  if(name==='@/lib/apps/registry')return {accentOf:()=>({})};
  if(name==='@/lib/commsStore')return {useCommsSession:()=>null};
  if(name==='./kit')return {WiredScreen:({children})=>children};
  if(name==='@/lib/customerComms')return {...api,saveContact:async(...a)=>{calls.push(a);return save()}};
  throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;effectCursor=0;const tree=scope.exports.ReceptionDesk({app:{},screen:{}});while(pending.length)pending.shift()();return tree};
 const find=(type,label)=>elements(render()).find(e=>e.type===type&&(e.props['aria-label']===label||e.props.children===label||e.props.title===label));
 const open=()=>{find('input','Phone number').props.onChange({target:{value:'5550100'}});find('button','Save to CRM').props.onClick()};
 return {render,find,open,calls};
}
test('cancelled contact creation never calls CRM',()=>{
 const h=harness(async()=>({name:'Fixture'}));h.open();h.find('button','Cancel').props.onClick();
 assert.equal(h.calls.length,0);assert.equal(h.find('form','Save contact to CRM'),undefined);
 assert.equal(h.find('input','Phone number').props.value,'5550100');
});
test('duplicate submission is blocked and confirmed save clears the draft',async()=>{
 let done;const h=harness(()=>new Promise(r=>{done=r}));h.open();
 h.find('input','Contact name (optional)').props.onChange({target:{value:' Fixture '}});
 const form=h.find('form','Save contact to CRM');form.props.onSubmit({preventDefault(){}});form.props.onSubmit({preventDefault(){}});
 assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0],['5550100','Fixture']);
 done({name:'Fixture'});await tick();assert.equal(h.find('form','Save contact to CRM'),undefined);assert.equal(h.find('input','Phone number').props.value,'');
});
test('failed save retains entered contact without leaking adapter details',async()=>{
 const h=harness(async()=>{throw Error('secret fixture detail')});h.open();h.find('input','Contact name (optional)').props.onChange({target:{value:'Fixture'}});
 h.find('form','Save contact to CRM').props.onSubmit({preventDefault(){}});await tick();
 assert.equal(h.find('input','Contact name (optional)').props.value,'Fixture');
 const alert=elements(h.render()).find(e=>e.props?.role==='alert');assert.match(alert.props.children,/could not be confirmed/);assert.doesNotMatch(alert.props.children,/secret/);
});

test('read failures expose retries and clearing search rejects a late response',async()=>{
 let providerCalls=0,recentCalls=0,searchCalls=0,finish;
 const h=harness(null,{
  fetchProviderStatus:async()=>{providerCalls++;throw Error('private provider');},
  fetchRecent:async()=>{recentCalls++;throw Error('private recent');},
  searchCustomers:async()=>{searchCalls++;if(searchCalls===1)throw Error('private search');return new Promise(r=>{finish=r});},
 });
 h.render();await tick();
 assert.ok(h.find('button','Retry provider status'));assert.ok(h.find('button','Retry recent conversations'));
 h.find('button','Retry provider status').props.onClick();h.find('button','Retry recent conversations').props.onClick();h.render();await tick();
 assert.equal(providerCalls,2);assert.equal(recentCalls,2);
 h.find('input','Search customers').props.onChange({target:{value:'Fixture'}});h.render();await new Promise(r=>setTimeout(r,270));
 assert.ok(h.find('button','Retry search'));
 assert.ok(!elements(h.render()).some(e=>typeof e.props?.children==='string'&&e.props.children.includes('No customers match')));
 h.find('button','Retry search').props.onClick();h.render();await new Promise(r=>setTimeout(r,270));
 h.find('input','Search customers').props.onChange({target:{value:''}});h.render();finish({results:[{id:'late',name:'Late private customer'}]});await tick();
 const rendered=JSON.stringify(h.render());assert.doesNotMatch(rendered,/Late private customer|private provider|private recent|private search|Searching…/);
});
