import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flatten=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flatten)];
function harness(approver, response, canEdit=true){
 const state=[];let cursor=0,rc=0,dirty=false,saving=false;const requests=[],refs=[];
 const scope={exports:{},fetch:async(url,options)=>{requests.push({url,options});if(response)return response(url,options);return {ok:false,json:async()=>({detail:'Action changed. Refresh before reviewing.'})};},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
  if(name==='react/jsx-runtime')return jsx;
  if(name==='react')return {useEffect:(fn,deps)=>{if(deps?.length===2)fn();},useRef:initial=>refs[rc++]??(refs[rc-1]={current:initial}),useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}};
  if(name.endsWith('/auth'))return {authHeaders:()=>({})};
  if(name.endsWith('/api'))return {API_BASE:'http://fictional.test'};
  return {default:{}};
 }};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/marketing/MarketingOperations.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{cursor=0;rc=0;return flatten(scope.exports.MarketingOperations({mode:'communications',canEdit,onDraftOpenChange:v=>dirty=v,onSavingChange:v=>saving=v}));};
 render();state[0]={agents:[],runs:[],events:[],channels:{},can_approve:approver,actions:[{id:'SYN-1',subject:'Fictional offer',body:'Test only',channel:'social',status:'draft',revision:2}]};
 return {render,requests,state,dirty:()=>dirty,saving:()=>saving};
}
test('reviewers can return work inline; authors cannot decide; failed review retains feedback',async()=>{
 assert.ok(!harness(false).render().some(e=>e.props?.children==='Request changes'));
 const h=harness(true);
 h.render().find(e=>e.props?.children==='Request changes').props.onClick();
 h.render().find(e=>e.type==='textarea').props.onChange({target:{value:'Clarify the fictional offer'}});
 h.render().find(e=>e.props?.['aria-label']==='Request draft changes').props.onSubmit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.requests.length,1);
 assert.deepEqual(JSON.parse(h.requests[0].options.body),{revision:2,decision:'reject',note:'Clarify the fictional offer'});
 assert.equal(h.render().find(e=>e.type==='textarea').props.value,'Clarify the fictional offer');
 assert.ok(h.render().some(e=>e.props?.role==='alert'&&e.props.children.includes('Action changed')));
});

test('daily review defaults to draft and returned work, pages all loaded matches and resets on filter',()=>{
 const h=harness(false);
 h.state[0].actions=Array.from({length:9},(_,i)=>({id:`SYN-${i}`,subject:`Task ${i}`,body:'Fictional',channel:'social',status:i===8?'approved':i%2?'rejected':'draft',revision:1}));
 const cards=()=>h.render().filter(e=>e.type==='article');
 assert.equal(cards().length,4);assert.deepEqual(cards().map(e=>e.key),['SYN-0','SYN-1','SYN-2','SYN-3']);
 h.render().find(e=>e.props?.children==='Next actions').props.onClick();
 assert.deepEqual(cards().map(e=>e.key),['SYN-4','SYN-5','SYN-6','SYN-7']);
 h.render().find(e=>e.type==='select'&&e.props.value==='needs_review').props.onChange({target:{value:'approved'}});
 assert.deepEqual(cards().map(e=>e.key),['SYN-8']);
 assert.equal(h.render().find(e=>e.props?.children==='Previous actions').props.disabled,true);
});

test('open reviewer form reports unfinished work and cannot be replaced by another action',()=>{
 const h=harness(true);h.render().find(e=>e.props.children==='Request changes').props.onClick();
 h.render().find(e=>e.type==='textarea').props.onChange({target:{value:'Keep this feedback'}});
 const tree=h.render();assert.equal(h.dirty(),true);
 for(const label of ['New channel draft','Edit draft','Request changes','Approve action'])assert.equal(tree.find(e=>e.props.children===label).props.disabled,true);
 tree.find(e=>e.props.children==='Keep current status').props.onClick();h.render();assert.equal(h.dirty(),false);
});


test('reconciliation freezes submitted evidence, prevents duplicate requests and preserves failed work',async()=>{
 let finish;const h=harness(true,()=>new Promise(resolve=>finish=resolve));
 h.state[0].actions[0].status='unknown';
 h.render().find(e=>e.type==='select'&&e.props.value==='needs_review').props.onChange({target:{value:'all'}});
 const open=()=>h.render().find(e=>e.props.children==='Record provider reconciliation').props.onClick();
 open();
 h.render().find(e=>e.type==='input'&&e.props.maxLength===200).props.onChange({target:{value:'SYN-REF'}});
 h.render().find(e=>e.type==='textarea').props.onChange({target:{value:'Fictional provider evidence'}});
 h.render().find(e=>e.type==='select'&&e.props.value==='accepted').props.onChange({target:{value:'delivered'}});
 const submit=h.render().find(e=>e.props['aria-label']==='Provider reconciliation').props.onSubmit;
 submit({preventDefault(){}});submit({preventDefault(){}});
 assert.equal(h.requests.length,1);
 assert.equal(h.render().find(e=>e.type==='fieldset').props.disabled,true);assert.equal(h.saving(),true);
 assert.deepEqual(JSON.parse(h.requests[0].options.body),{provider_reference:'SYN-REF',status:'delivered',evidence:'Fictional provider evidence'});
 finish({ok:false,json:async()=>({detail:'Fictional provider unavailable'})});await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.render().find(e=>e.type==='fieldset').props.disabled,false);assert.equal(h.saving(),false);
 assert.equal(h.render().find(e=>e.type==='textarea').props.value,'Fictional provider evidence');
 h.render().find(e=>e.props.children==='Keep current status').props.onClick();open();
 assert.ok(h.render().some(e=>e.type==='select'&&e.props.value==='accepted'));
 assert.equal(h.render().find(e=>e.type==='textarea').props.value,'');
});


test('read-only channel viewers retain records without author or reviewer controls',()=>{
 const h=harness(false,undefined,false);
 h.state[0].actions=['draft','rejected','approved','unknown','dispatching','delivered'].map((status,i)=>({id:`READ-${i}`,subject:`Fictional ${status}`,body:'Visible evidence',channel:'social',status,revision:1}));
 h.render().find(e=>e.type==='select'&&e.props.value==='needs_review').props.onChange({target:{value:'all'}});
 const forbidden=['New channel draft','Edit draft','Approve action','Request changes','Cancel action','Dispatch approved action','Record provider reconciliation'];
 for(let page=0;page<2;page++){
  const tree=h.render();assert.ok(tree.some(e=>e.type==='article'));
  for(const label of forbidden)assert.ok(!tree.some(e=>e.type==='button'&&e.props.children===label),label);
  if(page===0)tree.find(e=>e.props.children==='Next actions').props.onClick();
 }
 assert.equal(h.requests.length,0);
});

test('authors can revise returned work but cannot approve dispatch or reconcile it',()=>{
 const h=harness(false);h.state[0].actions[0].status='rejected';
 const tree=h.render();assert.ok(tree.some(e=>e.props.children==='Edit draft'));
 for(const label of ['Approve action','Request changes','Cancel action','Dispatch approved action','Record provider reconciliation'])assert.ok(!tree.some(e=>e.props.children===label),label);
 tree.find(e=>e.props.children==='Edit draft').props.onClick();
 assert.equal(h.render().find(e=>e.type==='textarea').props.value,'Test only');
 assert.equal(h.dirty(),true);assert.equal(h.requests.length,0);
});
