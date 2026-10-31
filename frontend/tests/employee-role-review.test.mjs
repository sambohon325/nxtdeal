import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flat=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flat)];
function harness(save){
 let cursor=0;const ref={current:false};const calls=[];
 const state=[[{role:'SALES',description:'Sales'},{role:'SERVICE',description:'Service'}],[{employee_id:'SYN1',name:'Fictional Employee',role:'SALES',has_login:true}],false];
 const scope={Error,exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:()=>{},useRef:()=>ref,useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}}:{updateUserRole:async(...args)=>{calls.push(args);return save(...args);}})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/UserManagementBoard.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{cursor=0;return flat(scope.exports.UserManagementBoard({theme:'light'}));};
 return{calls,render,choose:()=>render().find(e=>e.props['aria-label']==='Role for Fictional Employee').props.onChange({target:{value:'SERVICE'}}),button:label=>render().find(e=>e.type==='button'&&e.props.children===label)};
}
test('role selection is staged and cancellation sends no request',()=>{
 const h=harness(async()=>{});h.choose();assert.equal(h.calls.length,0);
 assert.ok(h.render().some(e=>e.props['aria-label']==='Review employee role change'));
 h.button('Cancel role change').props.onClick();assert.equal(h.calls.length,0);
 assert.equal(h.render().find(e=>e.type==='select').props.value,'SALES');
});
test('failed role save retains draft for retry and success updates roster',async()=>{
 let fail=true;const h=harness(async()=>{if(fail)throw Error('Connection unavailable');});h.choose();
 await h.button('Save role change').props.onClick();assert.ok(h.render().some(e=>e.props.role==='alert'&&e.props.children==='Connection unavailable'));
 assert.equal(h.render().find(e=>e.type==='select').props.value,'SERVICE');
 fail=false;await h.button('Save role change').props.onClick();assert.deepEqual(h.calls,[['SYN1','SERVICE'],['SYN1','SERVICE']]);
 assert.ok(!h.render().some(e=>e.props['aria-label']==='Review employee role change'));
 assert.equal(h.render().find(e=>e.type==='select').props.value,'SERVICE');
});
test('double save submits once and disables editing while pending',async()=>{
 let finish;const h=harness(()=>new Promise(resolve=>{finish=resolve;}));h.choose();
 const save=h.button('Save role change').props.onClick;const pending=save();await save();assert.equal(h.calls.length,1);
 assert.equal(h.button('Cancel role change').props.disabled,true);assert.equal(h.render().find(e=>e.type==='select').props.disabled,true);
 finish();await pending;
});
