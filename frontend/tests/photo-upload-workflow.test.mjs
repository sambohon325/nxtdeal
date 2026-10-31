import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const flatten=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(flatten)];
test('photo upload reports pending and retained draft on failure without duplicate submission',async()=>{
 const states=[],refs=[];let c=0,r=0,dirty=false,busy=false,finish,calls=0;
 const scope={exports:{},fetch:()=>{calls++;return new Promise(resolve=>finish=resolve);},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:fn=>fn(),useRef:i=>refs[r++]??(refs[r-1]={current:i}),useState:i=>{const k=c++;if(!(k in states))states[k]=i;return [states[k],v=>states[k]=v];}}:n.endsWith('/auth')?{authHeaders:()=>({})}:{API_BASE:'http://fictional.test'})};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../components/DealerCloudStorage.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{c=r=0;return flatten(scope.exports.DealerPhotoUpload({vehicleId:'SYN-V',onUploaded(){throw Error('must not succeed');},onBusyChange:v=>busy=v,onDraftChange:v=>dirty=v}));};
 render().find(e=>e.props.type==='file').props.onChange({target:{files:[{name:'fictional.png',size:10}]}});
 render().find(e=>e.props.type==='checkbox').props.onChange({target:{checked:true}});
 const click=render().find(e=>e.type==='button').props.onClick;click();click();
 assert.equal(calls,1);assert.equal(render()[0].props.disabled,true);assert.equal(busy,true);assert.equal(dirty,true);
 finish({ok:false,json:async()=>({detail:'Fictional upload failure'})});await new Promise(resolve=>setImmediate(resolve));
 render();assert.equal(busy,false);assert.equal(dirty,true);assert.ok(render().some(e=>e.props.role==='status'&&e.props.children==='Fictional upload failure'));
});
test('listing return waits for photo upload and protects an unsubmitted photo',()=>{
 const state=[];let c=0,closed=0,reportedBusy=false,reportedDraft=false;const Photo=()=>null;
 const scope={exports:{},require:n=>n.endsWith('/WorkspaceUi')?workControls:(n==='react/jsx-runtime'?jsx:n==='react'?{useEffect:(fn,deps)=>{if(deps.length===2)fn();},useState:i=>{const k=c++;if(!(k in state))state[k]=i;return [state[k],v=>state[k]=v];}}:n.includes('DealerCloudStorage')?{DealerPhotoUpload:Photo}:n.includes('productTheme')?{PRODUCT_ACCENT_COLORS:{}}:{})};
 const source=fs.readFileSync(new URL('../components/MerchandisingBoard.tsx',import.meta.url),'utf8').replace('function VehicleDetailModal(', 'export function VehicleDetailModal(');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,scope);
 const render=()=>{c=0;return flatten(scope.exports.VehicleDetailModal({theme:'dark',vehicleId:'SYN-V',onClose:()=>closed++,onChanged(){},onDraftOpenChange:v=>reportedDraft=v,onSavingChange:v=>reportedBusy=v}));};
 render();state[0]={vehicle:{vehicle_id:'SYN-V'},images:[],vdp_health:{},feed_status:{feeds:[]}};
 let tree=render();const photo=tree.find(e=>e.type===Photo);photo.props.onBusyChange(true);
 tree=render();const back=tree.find(e=>e.props.children==='Back to merchandising');assert.equal(back.props.disabled,true);assert.equal(reportedBusy,true);back.props.onClick();assert.equal(closed,0);
 photo.props.onBusyChange(false);photo.props.onDraftChange(true);render().find(e=>e.props.children==='Back to merchandising').props.onClick();
 assert.ok(render().some(e=>e.props.role==='alert'));assert.equal(reportedDraft,true);assert.equal(reportedBusy,false);assert.equal(closed,0);
 render().find(e=>e.props.children==='Discard draft and return').props.onClick();assert.equal(closed,1);
});

