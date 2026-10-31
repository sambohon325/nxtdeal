import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const code=ts.transpileModule(fs.readFileSync(new URL('../components/apps/screens/SalesBrand.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(api){
 const state=[], effects=[],pending=[];let cursor=0,ec=0;
 const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}];};
 const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
 if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0],useEffect:(fn,deps)=>{const i=ec++;if(!effects[i]||deps.some((v,j)=>v!==effects[i][j])){effects[i]=deps;pending.push(fn);}}};
 if(name==='react/jsx-runtime')return jsx;
 if(name==='./kit')return {WiredScreen:'frame'};
 if(name==='./FeaturedVehiclePicker')return {FeaturedVehiclePicker:'picker'};
 if(name==='./ParentWebsitePicker')return {ParentWebsitePicker:'parent-picker'};
 if(name==='./PersonalPageShare')return {PersonalPageShare:'share-kit'};
 if(name==='@/components/PersonalPage')return {PersonalPage:'preview'};
 if(name==='@/lib/websites')return api;
 throw Error(name);
 }};vm.runInNewContext(code,scope);
 const render=()=>{cursor=0;ec=0;const tree=scope.exports.SalesBrand({app:{},screen:{}});while(pending.length)pending.shift()();return tree;};
 return{render,find:type=>elements(render()).find(e=>e.type===type)};
}
const event={preventDefault(){}};
test('load failure stays distinct from absent page and supports retry',async()=>{
 let calls=0;const h=harness({getMyPersonalSite:async()=>{calls++;throw Error('private detail');}});h.render();await tick();
 const tree=h.render();assert.match(tree.props.error,/Unable/);assert.doesNotMatch(JSON.stringify(tree),/private detail/);tree.props.onRetry();h.render();await tick();assert.equal(calls,2);
});
test('creation blocks duplicate requests and reports draft only on confirmation',async()=>{
 let done,calls=0;const h=harness({getMyPersonalSite:async()=>null,createPersonalSite:slug=>{calls++;assert.equal(slug,'sam');return new Promise(r=>done=r);}});h.render();await tick();h.find('input').props.onChange({target:{value:'sam'}});
 const save=h.find('form').props.onSubmit;const p=save(event);await save(event);assert.equal(calls,1);assert.equal(h.find('input').props.disabled,true);done({id:'PS1',slug:'sam',status:'draft'});await p;assert.match(JSON.stringify(h.render()),/Draft created/);
});
test('failed edits retain draft and only submit editable fields',async()=>{
 let patch;const h=harness({getMyPersonalSite:async()=>({id:'PS1',slug:'sam',status:'active',employee_id:'E1',headline:'Before'}),updatePersonalSite:async(id,p)=>{patch=p;throw Error('private detail');}});h.render();await tick();h.find('input').props.onChange({target:{value:'After'}});await h.find('form').props.onSubmit(event);
 assert.equal(h.find('input').props.value,'After');assert.equal(patch.headline,'After');assert.equal('status' in patch,false);assert.equal('employee_id' in patch,false);assert.match(JSON.stringify(h.render()),/couldn't confirm/);assert.doesNotMatch(JSON.stringify(h.render()),/private detail/);
});

test('publication needs confirmation, blocks duplicates and exposes only confirmed live link',async()=>{
 let calls=0,done;const fixture={id:'PS1',slug:'sam',status:'draft'};
 const h=harness({getMyPersonalSite:async()=>fixture,setPersonalSiteStatus:async(id,status)=>{calls++;assert.equal(status,'active');return new Promise(r=>done=r);}});h.render();await tick();
 const button=label=>elements(h.render()).find(e=>e.type==='button'&&e.props.children===label);
 assert.equal(h.find('a'),undefined);button('Publish page').props.onClick();assert.equal(calls,0);button('Cancel').props.onClick();assert.equal(calls,0);
 button('Publish page').props.onClick();const confirm=button('Confirm publish');
 // Mixed JSX children form an array for the confirmation label.
 const action=elements(h.render()).find(e=>e.type==='button'&&JSON.stringify(e.props.children).includes('Confirm ')).props.onClick;
 const pending=action();await action();assert.equal(calls,1);done({...fixture,status:'active'});await pending;assert.equal(h.find('a').props.href,'/rep/sam');
});
test('unsaved content blocks preview/publication and failed status never invents success',async()=>{
 const fixture={id:'PS1',slug:'sam',status:'draft'};let calls=0;
 const h=harness({getMyPersonalSite:async()=>fixture,setPersonalSiteStatus:async()=>{calls++;throw Error('private');}});h.render();await tick();
 elements(h.render()).find(e=>e.type==='button'&&e.props.children==='Publish page').props.onClick();
 await elements(h.render()).find(e=>e.type==='button'&&JSON.stringify(e.props.children).includes('Confirm ')).props.onClick();
 assert.equal(calls,1);assert.equal(h.find('a'),undefined);assert.match(JSON.stringify(h.render()),/couldn't be confirmed/);
 h.find('input').props.onChange({target:{value:'Unsaved'}});
 for(const label of ['Publish page','Preview saved page'])assert.equal(elements(h.render()).find(e=>e.type==='button'&&e.props.children===label).props.disabled,true);
});
test('saved preview uses owner read without public publication or view-log endpoint',async()=>{
 let calls=0;const fixture={id:'PS1',slug:'sam',status:'draft',featured_vehicles:[]};
 const h=harness({getMyPersonalSite:async()=>fixture,getPersonalSite:async id=>{calls++;assert.equal(id,'PS1');return fixture;}});h.render();await tick();
 await elements(h.render()).find(e=>e.type==='button'&&e.props.children==='Preview saved page').props.onClick();
 assert.equal(calls,1);assert.equal(h.find('preview').props.site.slug,'sam');assert.equal(h.find('a'),undefined);
});
test('unpublish removes public link only after server confirmation',async()=>{
 const fixture={id:'PS1',slug:'sam',status:'active'};const h=harness({getMyPersonalSite:async()=>fixture,setPersonalSiteStatus:async(id,status)=>{assert.equal(status,'inactive');return{...fixture,status};}});h.render();await tick();
 elements(h.render()).find(e=>e.type==='button'&&e.props.children==='Unpublish page').props.onClick();assert.ok(h.find('a'));
 await elements(h.render()).find(e=>e.type==='button'&&JSON.stringify(e.props.children).includes('Confirm ')).props.onClick();assert.equal(h.find('a'),undefined);assert.match(JSON.stringify(h.render()),/no longer public/);
});

test('featured selection shares page save and invalidates saved preview',async()=>{
 let patch;const fixture={id:'PS1',slug:'sam',status:'draft',featured_vehicle_ids:[]};
 const h=harness({getMyPersonalSite:async()=>fixture,updatePersonalSite:async(id,p)=>{patch=p;return{...fixture,...p};}});h.render();await tick();
 h.find('picker').props.onChange(['V1']);
 assert.equal(elements(h.render()).find(e=>e.type==='button'&&e.props.children==='Preview saved page').props.disabled,true);
 await h.find('form').props.onSubmit(event);assert.deepEqual([...patch.featured_vehicle_ids],['V1']);
});

test('parent update guards duplicate requests and preserves current site on failure',async()=>{
 let calls=0,reject;const fixture={id:'PS1',slug:'sam',status:'draft',parent_website_id:'OLD'};
 const h=harness({getMyPersonalSite:async()=>fixture,setPersonalSiteParent:()=>{calls++;return new Promise((_,r)=>reject=r);}});h.render();await tick();
 const action=h.find('parent-picker').props.onApply;const pending=action('NEW');action('NEW');assert.equal(calls,1);assert.equal(h.find('parent-picker').props.disabled,true);reject(Error('secret'));await pending;
 assert.equal(h.find('parent-picker').props.current,'OLD');assert.match(JSON.stringify(h.render()),/could not be confirmed/);assert.doesNotMatch(JSON.stringify(h.render()),/secret/);
});

test('share kit is available only for confirmed active pages',async()=>{
 for(const status of ['draft','inactive','active']){
  const h=harness({getMyPersonalSite:async()=>({id:'PS1',slug:'sam',status})});h.render();await tick();assert.equal(Boolean(h.find('share-kit')),status==='active');
 }
});
