import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/PersonalPageShare.tsx',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(api, props){
 const state=[], effects=[],pending=[];let cursor=0,ec=0;
 const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}];};
 const scope={exports:{},URL,window:{location:{origin:'https://app.nxtdeal.app'}},navigator:{clipboard:{writeText:api.writeText}},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
 if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0],useEffect:(fn,deps)=>{const i=ec++;if(!effects[i]||deps.some((v,j)=>v!==effects[i][j])){effects[i]=deps;pending.push(fn);}}};
 if(name==='react/jsx-runtime')return jsx;
 if(name==='./kit')return {WiredScreen:'frame'};
 if(name==='./FeaturedVehiclePicker')return {FeaturedVehiclePicker:'picker'};
 if(name==='@/components/PersonalPage')return {PersonalPage:'preview'};
 if(name==='qrcode')return {default:{toDataURL:api.toDataURL}};
 throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;ec=0;const tree=scope.exports.PersonalPageShare(props);while(pending.length)pending.shift()();return tree;};
 return{render,find:type=>elements(render()).find(e=>e.type===type)};
}


test('QR and copy use the same encoded public URL, with copy confirmed after completion',async()=>{
 let encoded,copied,done;const h=harness({toDataURL:async url=>{encoded=url;return'data:image/png;base64,fixture';},writeText:url=>{copied=url;return new Promise(r=>done=r);}},{slug:'sam test'});
 h.render();await tick();const url='https://app.nxtdeal.app/rep/sam%20test';assert.equal(encoded,url);assert.equal(h.find('input').props.value,url);assert.equal(h.find('a').props.download,'nxtdeal-personal-page-qr.png');
 const copy=h.find('button').props.onClick;const pending=copy();await copy();assert.equal(copied,url);assert.doesNotMatch(JSON.stringify(h.render()),/Page link copied/);done();await pending;assert.match(JSON.stringify(h.render()),/Page link copied/);
});
test('QR and clipboard failures retain a manually usable link',async()=>{
 const h=harness({toDataURL:async()=>{throw Error('private');},writeText:async()=>{throw Error('private');}},{slug:'sam'});h.render();await tick();await h.find('button').props.onClick();
 assert.equal(h.find('img'),undefined);assert.equal(h.find('input').props.value,'https://app.nxtdeal.app/rep/sam');assert.match(JSON.stringify(h.render()),/Select and copy/);assert.match(JSON.stringify(h.render()),/QR code unavailable/);assert.doesNotMatch(JSON.stringify(h.render()),/private/);
});
