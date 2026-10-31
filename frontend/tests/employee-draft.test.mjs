import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const flat=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flat)];
const detail={employee:{attributes:{}},identity_and_access:{role:'SALES',lockout:{locked:false,failed_attempts:0},active_permission_overrides:[],api_keys:[],effective_permissions:[]},recent_activity:{total_events:0,events:[]}};
function harness(save=async()=>{throw Error("Connection unavailable");}){let cursor=0,closed=0,rc=0;const refs=[];const state=[detail,{categories:[]},null,'','read',true,'','',null];const scope={Error,exports:{},require:n=>{if(n.endsWith('/WorkspaceUi'))return workControls;
 if(n==='react/jsx-runtime')return jsx;if(n==='react')return{useRef:initial=>refs[rc++]??(refs[rc-1]={current:initial}),useEffect:()=>{},useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}};
 return {PRODUCT_ACCENT_COLORS:[],setIpAllowlist:save};
 }};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/AdminUsersBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 return{state,closed:()=>closed,render:()=>{cursor=0;rc=0;return flat(scope.exports.UserDetailWorkspace({theme:'dark',employeeId:'SYN1',onClose:()=>closed++,onChanged:()=>{}}));}};
}
test('employee IP draft survives failed save and cancelled directory exit',async()=>{
 const h=harness();let tree=h.render();assert.equal(tree.filter(e=>e.type==='details').length,5);
 tree.find(e=>e.props['aria-label']==='Employee IP allowlist').props.onChange({target:{value:'192.0.2.1'}});
 await h.render().find(e=>e.props.children==='Save').props.onClick();
 assert.equal(h.state[3],'192.0.2.1');assert.equal(h.state[2],'Connection unavailable');
 h.render().find(e=>e.props.children==='← Back to employee directory').props.onClick();assert.equal(h.closed(),0);
 h.render().find(e=>e.props.children==='Keep editing employee').props.onClick();assert.equal(h.state[3],'192.0.2.1');
 h.render().find(e=>e.props.children==='← Back to employee directory').props.onClick();h.render().find(e=>e.props.children==='Discard and return to directory').props.onClick();assert.equal(h.closed(),1);
});
test('unchanged employee can return immediately; a new key label requires a choice',()=>{
 const h=harness();h.render().find(e=>e.props.children==='← Back to employee directory').props.onClick();assert.equal(h.closed(),1);
 h.render().find(e=>e.props.placeholder==='Label for a new key').props.onChange({target:{value:'Synthetic integration'}});
 h.render().find(e=>e.props.children==='← Back to employee directory').props.onClick();assert.equal(h.closed(),1);assert.ok(h.render().some(e=>e.props.children==='Keep editing employee'));
});


test('pending employee mutation blocks duplicate save and directory exit, then recovers',async()=>{
 let rejectSave,calls=0;const h=harness(()=>{calls++;return new Promise((_,reject)=>{rejectSave=reject;});});
 const save=h.render().find(e=>e.props.children==='Save').props.onClick;
 const pending=save();await save();assert.equal(calls,1);
 let tree=h.render();assert.equal(tree.find(e=>e.type==='fieldset').props.disabled,true);
 const back=tree.find(e=>e.props.children==='← Back to employee directory');assert.equal(back.props.disabled,true);back.props.onClick();assert.equal(h.closed(),0);
 rejectSave(Error('Unavailable'));await pending;tree=h.render();assert.equal(tree.find(e=>e.type==='fieldset').props.disabled,false);
 tree.find(e=>e.props.children==='← Back to employee directory').props.onClick();assert.equal(h.closed(),1);
});
