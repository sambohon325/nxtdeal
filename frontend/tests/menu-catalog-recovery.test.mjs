import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const adminScope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../lib/administrationNavigation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,adminScope);
const source=ts.transpileModule(fs.readFileSync(new URL('../components/DepartmentMenuBar.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function harness(responses){let calls=0;const scope={exports:{},fetch:async()=>{calls++;return responses.shift();},require:name=>name==='@/lib/administrationNavigation'?adminScope.exports:name.endsWith('/WorkspaceUi')?workControls:(name==='@/lib/auth'?{authHeaders:()=>({})}:name==='@/lib/api'?{API_BASE:'http://fictional.invalid'}:{})};vm.runInNewContext(source,scope);return {load:scope.exports.fetchMenuCatalog,calls:()=>calls};}
const response=(data,ok=true)=>({ok,json:async()=>data});
test('navigation errors never become cached empty menus and retry recovers',async()=>{
 const items=[{key:'campaigns',label:'Campaigns'}];const h=harness([response({error:'Invalid or expired token'}),response({items})]);
 await assert.rejects(h.load('Marketing'),/expired token/);assert.equal(await h.load('Marketing'),items);assert.equal(h.calls(),2);
});
test('navigation reload reflects changed access instead of reusing department cache',async()=>{
 const h=harness([response({items:[{key:'campaigns',label:'Campaigns'}]}),response({items:[]})]);
 assert.equal((await h.load('Marketing')).length,1);assert.equal((await h.load('Marketing')).length,0);
});
test('navigation rejects HTTP failures and malformed catalogs',async()=>{
 for(const res of [response({},false),response({}),response({items:[{}]})])await assert.rejects(harness([res]).load('Service'));
});
