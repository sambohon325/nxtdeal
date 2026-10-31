import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const flat=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flat)];
test('audience changes invalidate displayed counts and ignore older pending previews',async()=>{
 let cursor=0,rc=0;const states=[],refs=[],pending=[];
 const scope={Error,exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:()=>{},useMemo:f=>f(),useRef:initial=>refs[rc++]??(refs[rc-1]={current:initial}),useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];}}:n==='@/lib/auth'?{getSession:()=>({role:'MARKETING'})}:{previewCrmAudience:()=>new Promise((resolve,reject)=>pending.push({resolve,reject}))})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/MarketingCRMBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const campaigns={available_types:[{key:'general',name:'General',audience_fields:[{key:'days',label:'Days',type:'number'}]}],available_channels:[],by_status:{},recent_campaigns:[],pending_drafts:{count:0},total_campaigns:0};
 const render=()=>{cursor=0;rc=0;return flat(scope.exports.CampaignsTab({theme:'dark',campaigns,onRefresh:()=>{},onClearPrefill:()=>{}}));};
 const button=text=>render().find(e=>e.type==='button'&&e.props.children===text);
 button('+ New Campaign').props.onClick();
 const first=button('Preview Audience').props.onClick();
 flat(render().find(e=>e.type==='label'&&e.key==='days')).find(e=>e.type==='input').props.onChange({target:{value:'30'}});
 pending[0].resolve({count:100});await first;assert.equal(states[9],null);
 const second=button('Preview Audience').props.onClick();const third=button('Preview Audience').props.onClick();
 pending[2].resolve({count:7});await third;assert.equal(states[9].count,7);
 pending[1].reject(Error('Old failure'));await second;assert.equal(states[9].count,7);assert.equal(states[11],null);
 flat(render().find(e=>e.type==='label'&&e.key==='days')).find(e=>e.type==='input').props.onChange({target:{value:'60'}});assert.equal(states[9],null);
});

