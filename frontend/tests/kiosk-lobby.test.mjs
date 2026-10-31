import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import {renderToStaticMarkup} from 'react-dom/server';
const fields={welcome:'Welcome',lounge:'Lounge',refreshments:'Refreshments',transport:'Transportation',accessibility:'Accessibility',guest_wifi:'Guest Wi-Fi'};
function harness(request){
 const code=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/KioskLobby.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;if(name==='react/jsx-runtime')return jsx;if(name==='./kit')return {useAsync:()=>request};if(name==='@/lib/lobbyInformation')return {LOBBY_FIELDS:fields};throw Error(name);}};
 vm.runInNewContext(code,scope); const tree=scope.exports.KioskLobby({screen:{heading:'While you wait'}});
 return {tree,html:renderToStaticMarkup(tree)};
}
test('drafts and empty content render honest empty states',()=>{
 for(const data of [{published:false,content:{welcome:'PRIVATE'}},{published:true,content:{}}]){
  const h=harness({data});assert.match(h.html,/has not published/);assert.doesNotMatch(h.html,/PRIVATE|Free coffee/);
 }
});
test('published content is escaped and limited to known fields',()=>{
 const h=harness({data:{published:true,content:{welcome:'<script>unsafe</script>',private_secret:'HIDDEN',lounge:{bad:'object'}}}});
 assert.match(h.html,/&lt;script&gt;/);assert.doesNotMatch(h.html,/<script>|HIDDEN|object Object/);
});
test('refresh errors hide previously visible details and allow retry',()=>{
 let retried=false;
 const h=harness({error:'internal error',data:{published:true,content:{welcome:'STALE'}},reload:()=>{retried=true;}});
 assert.match(h.html,/unavailable right now/);assert.doesNotMatch(h.html,/STALE|internal error/);
 h.tree.props.children.find(e=>e?.type==='button').props.onClick();assert.equal(retried,true);
});
test('loading hides cached content and disables refresh',()=>{
 const h=harness({loading:true,data:{published:true,content:{welcome:'STALE'}}});
 assert.match(h.html,/Loading lobby/);assert.doesNotMatch(h.html,/STALE/);
 assert.equal(h.tree.props.children.find(e=>e?.type==='button').props.disabled,true);
});
