import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const flat=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flat)];
test('campaign edit retains failed-save text, guards return and cancel restores saved values',async()=>{
 let cursor=0,closed=0,rc=0,calls=0,rejectSave;const refs=[];const states=[{campaign:{name:'Saved campaign',notes:'Saved notes'},stats:{status:'draft'},members:{}},1,25,'',false,'Saved campaign','Saved notes',false,null,null];
 const scope={Error,exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:()=>{},useMemo:f=>f(),useRef:initial=>refs[rc++]??(refs[rc-1]={current:initial}),useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];}}:n==='@/lib/auth'?{getSession:()=>({role:'MARKETING'})}:{updateCampaign:()=>{calls++;return new Promise((_,reject)=>{rejectSave=reject;});}})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/MarketingCRMBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{cursor=0;rc=0;return flat(scope.exports.CampaignDetailView({theme:'dark',campaignId:'SYN1',onBack:()=>closed++,onChanged:()=>{}}));};const button=s=>render().find(e=>e.type==='button'&&e.props.children===s);
 button('Edit').props.onClick();render().find(e=>e.props['aria-label']==='Campaign name').props.onChange({target:{value:'Unfinished'}});
 const save=button('Save').props.onClick;const pending=save();await save();assert.equal(calls,1);assert.equal(button('← Back to Campaigns').props.disabled,true);rejectSave(Error('Offline'));await pending;assert.ok(render().some(e=>e.props.children==='Offline'));
 button('← Back to Campaigns').props.onClick();assert.equal(closed,0);button('Keep editing campaign').props.onClick();assert.equal(render().find(e=>e.props['aria-label']==='Campaign name').props.value,'Unfinished');
 button('Cancel').props.onClick();button('Edit').props.onClick();assert.equal(render().find(e=>e.props['aria-label']==='Campaign name').props.value,'Saved campaign');
 button('← Back to Campaigns').props.onClick();button('Discard edits and return').props.onClick();assert.equal(closed,1);
});
