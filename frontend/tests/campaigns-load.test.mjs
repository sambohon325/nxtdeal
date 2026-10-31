import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/CampaignsBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function harness(){
 const states=[],effects=[],requests=[];let cursor=0;
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react'?{
  useEffect:fn=>effects.push(fn),useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];}
 }:name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:name.includes('marketingCrm')?{fetchCampaignsData:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))}:{CampaignsTab:'CampaignsTab'})};
 vm.runInNewContext(source,scope);
 return {states,requests,render:()=>{cursor=0;effects.length=0;return scope.exports.CampaignsBoard({theme:'light'});},start:()=>effects[0]()};
}
function find(tree,type){if(!tree)return null;if(Array.isArray(tree)){for(const child of tree){const found=find(child,type);if(found)return found;}return null;}return tree.type===type?tree:find(tree.props?.children,type);}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('campaign load failure offers retry and cancelled response cannot restore stale data',async()=>{
 const h=harness();h.render();const cancel=h.start();cancel();h.requests[0].resolve({id:'OLD'});await settle();assert.equal(h.states[0],null);
 h.render();h.start();h.requests[1].reject(new Error('Offline'));await settle();
 const retry=find(h.render(),'button');assert.equal(retry.props.children,'Retry campaigns');retry.props.onClick();assert.equal(h.states[3],1);
 h.render();h.start();const recovered={id:'RECOVERED'};h.requests[2].resolve(recovered);await settle();assert.equal(h.states[0],recovered);
});
test('refresh failure preserves campaign work but disables stale controls until recovery',async()=>{
 const h=harness();h.render();h.start();const records={id:'SYNTHETIC'};h.requests[0].resolve(records);await settle();
 find(h.render(),'CampaignsTab').props.onRefresh();h.render();h.start();
 assert.equal(find(h.render(),'fieldset').props.disabled,true);
 h.requests[1].reject(new Error('Offline'));await settle();
 assert.equal(find(h.render(),'CampaignsTab').props.campaigns,records);assert.equal(find(h.render(),'fieldset').props.disabled,true);
 find(h.render(),'button').props.onClick();h.render();h.start();h.requests[2].resolve({id:'NEW'});await settle();
 assert.equal(find(h.render(),'fieldset').props.disabled,false);
});
