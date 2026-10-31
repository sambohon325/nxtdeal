import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/MarketingCRMBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function nodes(x){return !x||typeof x!=='object'?[]:[x,...[x.props?.children].flat(Infinity).flatMap(nodes)];}
test('campaign cancel keeps entered name until explicit inline discard',()=>{
 const states=[];let cursor=0;
 const scope={exports:{},require:name=>name.endsWith('/WorkspaceUi')?workControls:(name==='react'?{useRef:()=>({current:false}),useEffect:()=>{},useMemo:fn=>fn(),useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];}}:name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:name==='@/lib/auth'?{getSession:()=>({role:'MARKETING'})}:new Proxy({}, {get:(_,key)=>key}))};
 vm.runInNewContext(source,scope);
 const campaigns={available_types:[],available_channels:[],by_status:{},recent_campaigns:[{id:'SYN-C1',name:'Fictional existing',audience_count:0,status:'draft'}],pending_drafts:{count:0},total_campaigns:0};
 const render=()=>{cursor=0;return nodes(scope.exports.CampaignsTab({theme:'dark',campaigns,prefillType:null,onClearPrefill:()=>{},onRefresh:()=>{}}));};
 const button=text=>render().find(x=>x.type==='button'&&x.props.children===text);
 button('+ New Campaign').props.onClick();
 const input=render().find(x=>x.type==='input'&&x.props.placeholder==='New Campaign');
 // The name input is the first input in the empty-type form.
 (input||render().find(x=>x.type==='input')).props.onChange({target:{value:'Fictional unsaved draft'}});
 button('Cancel').props.onClick();assert.ok(button('Keep editing'));button('Keep editing').props.onClick();
 assert.ok(render().some(x=>x.type==='input'&&x.props.value==='Fictional unsaved draft'));
 const row=()=>render().find(x=>x.type==='button'&&nodes(x).some(n=>n.props?.children==='Fictional existing'));
 row().props.onClick();assert.ok(button('Discard draft and open campaign'));button('Keep editing').props.onClick();
 assert.ok(render().some(x=>x.type==='input'&&x.props.value==='Fictional unsaved draft'));
 row().props.onClick();button('Discard draft and open campaign').props.onClick();
 const detail=render().find(x=>x.props?.campaignId==='SYN-C1');assert.ok(detail);detail.props.onBack();assert.ok(button('+ New Campaign'));

 button('+ New Campaign').props.onClick();assert.equal(render().some(x=>x.type==='input'&&x.props.value==='Fictional unsaved draft'),false);
});

