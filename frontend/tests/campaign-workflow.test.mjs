import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flatten=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flatten)];
function harness(request){
 let cursor=0;const state={};const scope={exports:{},crypto:{randomUUID:()=> 'response-reference'},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useEffect(){},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v]}}:name==='@/lib/salesCrm'?{crmRequest:request}:{default:{}})};
 const source=fs.readFileSync(new URL('../components/marketing/CampaignWorkflow.tsx',import.meta.url),'utf8')+'\nexports.DetailForTest=WorkDetail;';
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 return {state,render(){cursor=0;return flatten(scope.exports.CampaignWorkflow({}));},detail(work){cursor=0;return flatten(scope.exports.DetailForTest({work,owners:[],onDirty(){},onBusy(){},onSaved(){},onClose(){}}));}};
}
const button=(tree,name)=>tree.find(e=>e.type==='button'&&e.props.children===name);
const settle=()=>new Promise(r=>setImmediate(r));
test('failed response save preserves evidence and unique reference for retry',async()=>{
 const h=harness(async()=>{throw Error('Save unavailable')});
 button(h.render(),'Record campaign response').props.onClick();
 h.state[3]={...h.state[3],brief_id:'B1',person_id:'C1',evidence:'Keep this customer request'};
 h.render().find(e=>e.type==='form').props.onSubmit({preventDefault(){}});await settle();
 assert.equal(h.state[3].evidence,'Keep this customer request');assert.equal(h.state[3].event_key,'response-reference');
 assert.ok(h.render().some(e=>e.props.role==='alert'&&e.props.children==='Save unavailable'));
});
test('passive signal remains passive in submitted request',async()=>{
 let saved;const h=harness(async(url,init)=>{if(init){saved=JSON.parse(init.body);return {}}return {cases:[],briefs:[],owners:[],signal_count:1,automation:''}});
 button(h.render(),'Record campaign response').props.onClick();h.state[3]={...h.state[3],kind:'click',brief_id:'B1',person_id:'C1',evidence:'Recorded click reference'};
 h.render().find(e=>e.type==='form').props.onSubmit({preventDefault(){}});await settle();
 assert.equal(saved.kind,'click');assert.equal(h.state[3],null);
});
test('failed workflow update retains correction evidence and shows error',async()=>{
 const h=harness(async()=>{throw Error('Record changed. Refresh first')});
 const w={id:'W1',revision:3,person_name:'QA',person_id:'C1',campaign_id:'CAMP1',department:'Service',owner_id:'E1',due_at:'2026-11-01T12:00:00Z',next_step:'Confirm time',stage:'response_due',reason:'reply',closed:false,recorded_value:null,history:[]};
 button(h.detail(w),'Update owner / next step').props.onClick();h.state[5]='Keep correction evidence';
 h.detail(w).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});await settle();
 assert.equal(h.state[0],'edit');assert.equal(h.state[5],'Keep correction evidence');assert.ok(h.detail(w).some(e=>e.props.role==='alert'));
});
