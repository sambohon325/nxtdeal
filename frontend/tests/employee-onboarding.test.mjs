import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';import vm from 'node:vm';import ts from 'typescript';import * as jsx from 'react/jsx-runtime';
const flat=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flat)];
function harness(create){
 let cursor=0,rc=0,dirty=false,saving=false;const refs=[],calls=[];
 const state=[[{role:'SALES',description:'Sales'}],[{employee_id:'SYN1',name:'Fictional',role:'SALES',has_login:true}],false];
 const scope={Error,exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:fn=>{if(fn.name!=='refresh')fn();},useRef:initial=>refs[rc++]??(refs[rc-1]={current:initial}),useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}}:{createUser:async input=>{calls.push(input);return create(input);},listRoles:async()=>({roles:state[0]}),listUsers:async()=>({users:state[1]})})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/UserManagementBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{cursor=0;rc=0;return flat(scope.exports.UserManagementBoard({theme:'light',onDraftOpenChange:v=>dirty=v,onSavingChange:v=>saving=v}));};
 return{calls,render,dirty:()=>dirty,saving:()=>saving,button:label=>render().find(e=>e.type==='button'&&e.props.children===label),fill:(label,value)=>render().find(e=>e.props['aria-label']===label).props.onChange({target:{value}})};
}
function start(h){h.button('+ Add user').props.onClick();h.fill('First name',' Fictional ');h.fill('Last name',' Employee ');}
test('hidden onboarding retains entries and navigation protection; failure keeps entered values',async()=>{
 const h=harness(async()=>{throw Error('Save failed');});start(h);h.render();assert.equal(h.dirty(),true);
 h.button('Hide setup').props.onClick();assert.ok(h.button('Resume staff setup'));assert.equal(h.dirty(),true);
 h.button('Resume staff setup').props.onClick();await h.button('Create user').props.onClick();
 assert.ok(h.render().some(e=>e.props.role==='alert'&&e.props.children==='Save failed'));
 assert.equal(h.render().find(e=>e.props['aria-label']==='First name').props.value,' Fictional ');
});
test('create submits once, trims names and protects login handoff until acknowledgement',async()=>{
 let finish;const h=harness(()=>new Promise(resolve=>finish=resolve));start(h);
 const save=h.button('Create user').props.onClick;const pending=save();await save();assert.equal(h.calls.length,1);assert.equal(h.calls[0].first_name,'Fictional');
 assert.equal(h.render().find(e=>e.type==='fieldset').props.disabled,true);assert.equal(h.saving(),true);
 finish({employee_id:'SYN2',name:'Fictional Employee',role:'SALES',temp_password:'fake-test-only'});await pending;
 assert.ok(h.render().some(e=>e.props['aria-label']==='New employee login handoff'));assert.equal(h.dirty(),true);assert.equal(h.saving(),false);assert.equal(h.button('+ Add user').props.disabled,true);
 h.button('I have recorded the login handoff').props.onClick();h.render();assert.equal(h.dirty(),false);
 assert.ok(!h.render().some(e=>e.props['aria-label']==='New employee login handoff'));
});
test('whitespace-only required names cannot create a login',async()=>{
 const h=harness(async()=>{});start(h);h.fill('First name','   ');assert.equal(h.button('Create user').props.disabled,true);
 await h.button('Create user').props.onClick();assert.equal(h.calls.length,0);
});
