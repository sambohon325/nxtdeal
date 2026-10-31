import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/LobbyInformationEditor.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(api){
 const state=[],effects=[],pending=[];let cursor=0,ec=0;
 const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}];};
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
 if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0],useEffect:(fn,deps)=>{const i=ec++;if(!effects[i]||deps.some((v,j)=>v!==effects[i][j])){effects[i]=deps;pending.push(fn);}}};
 if(name==='react/jsx-runtime')return jsx;
 if(name==='@/lib/lobbyInformation')return{LOBBY_FIELDS:{welcome:'Welcome'},...api};
 throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;ec=0;const tree=scope.exports.LobbyInformationEditor();while(pending.length)pending.shift()();return tree;};
 return{render,find:type=>elements(render()).find(e=>e.type===type),button:label=>elements(render()).find(e=>e.type==='button'&&e.props.children===label)};
}
const draft={published:false,content:{welcome:'Hello'}};
test('denied/failed load hides editing and retries without private error',async()=>{
 let calls=0;const h=harness({getLobbySettings:async()=>{if(++calls===1)throw Error('secret');return draft;}});
 h.render();await tick();assert.equal(h.find('textarea'),undefined);assert.doesNotMatch(JSON.stringify(h.render()),/secret/);
 await h.button('Try again').props.onClick();assert.equal(h.find('textarea').props.value,'Hello');
});
test('draft save retains edits on failure and blocks duplicate requests',async()=>{
 let reject,calls=0;const h=harness({getLobbySettings:async()=>draft,saveLobbySettings:(content,published)=>{calls++;assert.equal(content.welcome,'Edited');assert.equal(published,false);return new Promise((_,r)=>reject=r);}});
 h.render();await tick();h.find('textarea').props.onChange({target:{value:'Edited'}});
 const action=h.button('Save draft').props.onClick;action();action();assert.equal(calls,1);assert.equal(h.find('fieldset').props.disabled,true);
 reject(Error('secret'));await tick();assert.equal(h.find('textarea').props.value,'Edited');assert.match(JSON.stringify(h.render()),/could not be confirmed/);assert.doesNotMatch(JSON.stringify(h.render()),/secret/);
});
test('publication is explicit, cancellable and confirmed only after response',async()=>{
 let calls=0,done;const h=harness({getLobbySettings:async()=>draft,saveLobbySettings:(content,published)=>{calls++;assert.equal(published,true);return new Promise(r=>done=()=>r({...draft,published:true}));}});
 h.render();await tick();h.button('Publish information').props.onClick();assert.equal(calls,0);h.button('Cancel').props.onClick();assert.equal(calls,0);
 h.button('Publish information').props.onClick();const action=h.button('Confirm publish').props.onClick;const pending=action();action();assert.equal(calls,1);assert.equal(h.find('fieldset').props.disabled,true);
 assert.equal(h.button('Unpublish and save draft'),undefined);done();await pending;assert.ok(h.button('Unpublish and save draft'));
});
test('unpublishing confirms removal and saves the edited draft',async()=>{
 const h=harness({getLobbySettings:async()=>({...draft,published:true}),saveLobbySettings:async(content,published)=>{assert.equal(published,false);assert.equal(content.welcome,'New draft');return{...draft,content,published};}});
 h.render();await tick();h.find('textarea').props.onChange({target:{value:'New draft'}});h.button('Unpublish and save draft').props.onClick();assert.ok(h.button('Confirm unpublish'));
 await h.button('Confirm unpublish').props.onClick();assert.ok(h.button('Save draft'));assert.match(JSON.stringify(h.render()),/not public/);
});
