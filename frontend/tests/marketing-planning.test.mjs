import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flatten=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flatten)];
const source=fs.readFileSync(new URL('../components/marketing/CampaignPlanning.tsx',import.meta.url),'utf8');
function harness(request){
 let cursor=0;const state={};const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react/jsx-runtime'?jsx:name==='react'?{useEffect(){},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v]}}:name==='@/lib/salesCrm'?{crmRequest:request}:{default:{}})};
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 return {state,render(canEdit=true){cursor=0;return flatten(scope.exports.CampaignPlanning({canEdit}));}};
}
test('failed brief saves keep entered work and expose error',async()=>{
 const h=harness(async()=>{throw Error('Save unavailable')});
 h.render().find(e=>e.type==='button'&&e.props.children==='New campaign brief').props.onClick();
 h.state[1]={...h.state[1],name:'Retain this brief',audience_id:'LIST-EXISTING'};
 await h.render().find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.state[1].name,'Retain this brief');assert.equal(h.state[1].audience_id,'LIST-EXISTING');
 assert.ok(h.render().some(e=>e.props.role==='alert'&&e.props.children==='Save unavailable'));
});
test('saving edits sends canonical references and revision without server metadata',async()=>{
 let captured;const h=harness(async(path,init)=>{captured={path,body:JSON.parse(init.body)};return {...captured.body,id:'BRIEF-1',revision:4}});
 h.render().find(e=>e.type==='button'&&e.props.children==='New campaign brief').props.onClick();
 h.state[2]={...h.state[1],id:'BRIEF-1',revision:3};
 h.state[1]={...h.state[1],id:'BRIEF-1',revision:3,capacity_review:'unknown',name:'Changed',campaign_id:'CRMSEQ-EXISTING',audience_id:'LIST-EXISTING'};
 await h.render().find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(captured.path,'/marketing/planning/BRIEF-1');assert.equal(captured.body.revision,3);
 assert.equal(captured.body.campaign_id,'CRMSEQ-EXISTING');assert.equal(captured.body.audience_id,'LIST-EXISTING');
 assert.ok(!('capacity_review' in captured.body));assert.ok(!('id' in captured.body));assert.equal(h.state[2].revision,4);
});
test('readers cannot create campaign briefs',()=>{assert.ok(!harness(()=>{}).render(false).some(e=>e.type==='button'&&e.props.children==='New campaign brief'))});
test('Marketing owns demand tools while person-level conversations route to BDC',()=>{
 const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/bdcNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
 for(const key of ['campaigns','campaign_library','campaign_scheduler','leads','lists','audiences_scoring','journey_plans','execution','communications'])assert.equal(scope.exports.bdcDestination('Marketing',key),null,key);
 assert.equal(scope.exports.bdcDestination('Marketing','conversations'),'conversations');
});
