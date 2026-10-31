import {workControls} from './work-controls-stub.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';

function load(path, dependencies, extra={}) {
  const scope={exports:{},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;if(name in dependencies)return dependencies[name];throw Error(name);},...extra};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL(path,import.meta.url),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX},
  }).outputText,scope);
  return scope.exports;
}
function hooks() {
  const slots=[];let index=0;const effects=[];
  const react={
    useState:initial=>{const i=index++;if(!(i in slots))slots[i]=initial;return [slots[i],value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];},
    useRef:initial=>{const i=index++;if(!(i in slots))slots[i]={current:initial};return slots[i];},
    useCallback:fn=>fn,useMemo:fn=>fn(),useEffect:fn=>effects.push(fn),
  };
  return {react,effects,render:fn=>{index=0;return fn();}};
}
function messagingHarness() {
  const h=hooks();let session={token:'fictional-session',employeeId:'SYN-1'},fetcher=async()=>({ok:true,status:200,json:async()=>[]}),socket;
  const api=load('../lib/useMessaging.ts',{
    react:h.react,'@/lib/api':{API_BASE:'http://synthetic.test'},
    '@/lib/auth':{getSession:()=>session,authHeaders:()=>({}),clearSession:()=>{session=null;},isAuthError:value=>value?.error==='Invalid or expired token'},
  },{fetch:(...args)=>fetcher(...args),WebSocket:class {constructor(){socket=this;}close(){}}});
  return {render:()=>h.render(api.useMessaging),fetch:fn=>{fetcher=fn;},session:value=>{session=value;},getSession:()=>session,
    connect:()=>{h.effects.at(-1)();return socket;}};
}
const saved={id:'MSG-SYN-1',kind:'direct',sender_id:'SYN-1',recipient_id:'SYN-2',content:'Fictional handoff',timestamp:'2026-10-07T19:00:00Z',attached_pin:null};
const response=(data,status=200)=>({ok:status<400,status,json:async()=>data});

test('failed history and directory loads are errors, and successful empty retries are ready',async()=>{
  const h=messagingHarness();h.fetch(async()=>{throw Error('offline');});let m=h.render();
  await Promise.all([m.refreshChannels(),m.refreshDirectory(),m.loadDirect('SYN-2'),m.loadChannel('sales')]);m=h.render();
  assert.equal(m.channelStatus,'error');assert.equal(m.directoryStatus,'error');
  assert.equal(m.threadStatus['dm:SYN-2'],'error');assert.equal(m.threadStatus['channel:sales'],'error');
  h.fetch(async()=>response([]));await Promise.all([m.refreshChannels(),m.refreshDirectory(),m.loadDirect('SYN-2')]);m=h.render();
  assert.equal(m.channelStatus,'ready');assert.equal(m.directoryStatus,'ready');assert.equal(m.threadStatus['dm:SYN-2'],'ready');
});
test('REST save acknowledgement is visible without a socket and deduplicates a later push',async()=>{
  const h=messagingHarness();let m=h.render();const socket=h.connect();await Promise.resolve();
  h.fetch(async()=>response(saved));await m.sendDirect('SYN-2',saved.content);m=h.render();
  assert.equal(m.messages['dm:SYN-2'].length,1);
  socket.onmessage({data:JSON.stringify({event:'direct_message',message:saved})});m=h.render();
  assert.equal(m.messages['dm:SYN-2'].length,1);
});
test('failed and unconfirmed message saves reject instead of appearing successful',async()=>{
  for(const result of [response({error:'denied'},403),response({},200),response({error:'Invalid or expired token'},401)]) {
    const h=messagingHarness();h.fetch(async()=>result);const m=h.render();
    await assert.rejects(m.sendDirect('SYN-2','draft'));assert.equal(h.render().messages['dm:SYN-2'],undefined);
  }
});
test('late auth failure cannot erase a replacement session or append its old response',async()=>{
  for(const result of [response({error:'Invalid or expired token'},401),response(saved)]) {
    const h=messagingHarness();let resolve;h.fetch(()=>new Promise(done=>{resolve=done;}));
    const pending=h.render().sendDirect('SYN-2','draft');h.session({token:'replacement',employeeId:'SYN-3'});resolve(result);
    await assert.rejects(pending);assert.equal(h.getSession().token,'replacement');assert.equal(h.render().messages['dm:SYN-2'],undefined);
  }
});
function elements(tree,type) {
  if(!tree||typeof tree!=='object')return [];
  return [...(tree.type===type?[tree]:[]),...[tree.props?.children].flat(Infinity).flatMap(child=>elements(child,type))];
}
function screenHarness(send) {
  const h=hooks();const m={connected:true,channels:[],channelStatus:'ready',directoryStatus:'ready',threadStatus:{'dm:SYN-2':'ready','dm:SYN-3':'ready'},
    directory:[{employee_id:'SYN-2',name:'Fictional Sales'},{employee_id:'SYN-3',name:'Fictional Service'}],messages:{},unread:{},myEmployeeId:'SYN-1',
    sendDirect:send,refreshDirectory:()=>{},refreshChannels:()=>{},refreshConversations:()=>{},loadDirect:()=>{},markOpen:()=>{},markClosed:()=>{}};
  const api=load('../components/apps/screens/ReceptionTeamChat.tsx',{
    react:h.react,'react/jsx-runtime':jsx,'@/lib/apps/registry':{accentOf:()=>({})},'./kit':{WiredScreen:({children})=>children},
    '@/lib/useMessaging':{useMessaging:()=>m,channelThreadKey:id=>`channel:${id}`,directThreadKey:id=>`dm:${id}`},
  });
  const render=()=>h.render(()=>api.ReceptionTeamChat({app:{},screen:{}}));
  const choose=name=>elements(render(),'button').find(b=>renderToStaticMarkup(b).includes(name)).props.onClick();
  return {render,choose,m};
}
test('failed send retains the right recipient draft, prevents duplicate clicks and can recover',async()=>{
  let reject,resolve,calls=0;const h=screenHarness(()=>{calls++;return new Promise((ok,fail)=>{resolve=ok;reject=fail;});});
  h.choose('Fictional Sales');elements(h.render(),'input')[0].props.onChange({target:{value:'Keep this fictional draft'}});
  let tree=h.render();const button=elements(tree,'button').find(b=>b.props.children==='Send');
  const first=button.props.onClick();await button.props.onClick();assert.equal(calls,1);
  tree=h.render();assert.equal(elements(tree,'input')[0].props.disabled,true);
  reject(Error('offline'));await first;tree=h.render();
  assert.equal(elements(tree,'input')[0].props.value,'Keep this fictional draft');assert.match(renderToStaticMarkup(tree),/could not be confirmed/);
  h.choose('Fictional Service');assert.equal(elements(h.render(),'input')[0].props.value,'');
  h.choose('Fictional Sales');assert.equal(elements(h.render(),'input')[0].props.value,'Keep this fictional draft');
  const retry=elements(h.render(),'button').find(b=>b.props.children==='Send').props.onClick();resolve();await retry;
  assert.equal(elements(h.render(),'input')[0].props.value,'');
});
test('failed histories never render the empty conversation claim',()=>{
  const h=screenHarness(async()=>{});h.m.threadStatus['dm:SYN-2']='error';h.choose('Fictional Sales');
  const html=renderToStaticMarkup(h.render());assert.match(html,/history is unavailable/);assert.ok(!html.includes('No messages yet'));
});
