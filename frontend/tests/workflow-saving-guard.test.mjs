import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function harness(name){
 const states=[],effects=[],notices=[];let cursor=0;let requests=[];
 const source=ts.transpileModule(fs.readFileSync(new URL(`../components/${name}.tsx`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:id=>id==='react'?{useState:initial=>{const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v}]},useEffect:fn=>effects.push(fn)}:id==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:id.includes('/salesCrm')?{crmRequest:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))}:id.includes('/auth')?{getSession:()=>({role:'ADMIN',employeeId:'TEST'})}:new Proxy({},{get:(_,key)=>key})};
 vm.runInNewContext(source,scope);
 function render(){cursor=0;effects.length=0;return scope.exports[name]({onSavingChange:v=>notices.push(v)});}
 return {render,effects,notices,requests};
}
for(const name of ['FloorplanWorkBoard','CommissionWorkBoard','ReadinessPolicyBoard','SchemaMappingBoard'])test(`${name}: pending record loads do not announce an in-progress save`,async()=>{
 const h=harness(name);h.render();h.effects[2]();assert.equal(h.requests.length,1);h.render();h.effects[1]();assert.equal(h.notices.at(-1),false);h.requests[0].reject(new Error('Network unavailable'));await new Promise(r=>setImmediate(r));h.render();h.effects[1]();assert.equal(h.notices.at(-1),false);
});
function find(node,predicate){if(!node||typeof node!=='object')return; if(predicate(node))return node;for(const x of [node.props?.children].flat(Infinity)){const r=find(x,predicate);if(r)return r;}}
test('floorplan mutation announces saving until the write and refreshed records finish',async()=>{
 const h=harness('FloorplanWorkBoard');let tree=h.render();find(tree,n=>n.props?.children==='Record financing').props.onClick();tree=h.render();find(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});h.render();h.effects[1]();assert.equal(h.notices.at(-1),true);h.requests[0].resolve({});await new Promise(r=>setImmediate(r));h.render();h.effects[1]();assert.equal(h.notices.at(-1),true);h.requests[1].resolve({accounts:[],payoffs:[],vehicles:[],execution:''});await new Promise(r=>setImmediate(r));h.render();h.effects[1]();assert.equal(h.notices.at(-1),false);
});
