import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/kiosk/RestrictedLobby.tsx',import.meta.url),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX},
}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
function harness(hidden = false) {
  const state=[], effects=[], clients=[], listeners=new Map(), timers=new Map();
  let cursor=0, effectIndex=0, timerId=0, privacy;
  let grant={token:'fictional',deviceId:'lobby',apiOrigin:'https://example.test',expiresAt:100};
  const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];};
  const document={visibilityState:hidden?'hidden':'visible',addEventListener:(k,v)=>listeners.set(k,v),removeEventListener:k=>listeners.delete(k)};
  const scope={exports:{},document,Date:{now:()=>1000},setTimeout:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;},
    clearTimeout:id=>timers.delete(id),window:{addEventListener:(k,v)=>listeners.set(k,v),removeEventListener:k=>listeners.delete(k)},
    require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
      if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0],useEffect:(fn,deps)=>{
        const i=effectIndex++, previous=effects[i];
        if(!previous||deps.some((v,j)=>!Object.is(v,previous.deps[j])))effects[i]={fn,deps,cleanup:previous?.cleanup,pending:true};
      }};
      if(name==='react/jsx-runtime')return jsx;
      if(name==='@/lib/kioskPrivacy')return{startKioskPrivacyTimer:(warning,expire)=>{privacy={warning,expire,stopped:false,stop(){this.stopped=true;}};return privacy;}};
      if(name==='@/lib/restrictedKiosk')return{createRestrictedKiosk:()=>{
        const client={closed:0,requests:[],close(){this.closed++;},submit(fields){this.requests.push(fields);return new Promise(r=>this.finish=r);}};
        clients.push(client);return client;
      }};
      throw Error(name);
    }};
  vm.runInNewContext(source,scope);
  function render(){cursor=0;effectIndex=0;let tree=scope.exports.RestrictedLobby({grant});
    const pending=effects.filter(e=>e.pending);if(pending.length){for(const e of pending){e.cleanup?.();e.cleanup=e.fn();e.pending=false;}return render();}return tree;}
  return{render,clients,listeners,timers,privacy:()=>privacy,
    visibility:value=>{document.visibilityState=value;listeners.get('visibilitychange')?.();},
    update:change=>{grant={...grant,...change};return render();},
    fill:value=>elements(render()).find(e=>e.type==='input').props.onChange({target:{value}}),
    submit:()=>elements(render()).find(e=>e.type==='form').props.onSubmit({preventDefault(){}}),
    unmount:()=>effects.forEach(e=>e.cleanup?.())};
}
test('hiding a kiosk clears its draft and returning cannot reopen it',()=>{
  const h=harness();h.render();h.fill('Fictional Private Visitor');
  h.visibility('hidden');
  assert.match(JSON.stringify(h.render()),/front desk to reopen/);
  assert.doesNotMatch(JSON.stringify(h.render()),/Fictional Private Visitor/);
  assert.equal(h.clients[0].closed,1);
  h.visibility('visible');h.update({});
  assert.match(JSON.stringify(h.render()),/front desk to reopen/);
  h.unmount();assert.equal(h.listeners.size,0);
});
test('hidden kiosk discards pending success and remains closed',async()=>{
  const h=harness();h.render();h.fill('Fictional Visitor');const work=h.submit();
  h.visibility('hidden');h.clients[0].finish('confirmed');await work;
  h.visibility('visible');
  assert.match(JSON.stringify(h.render()),/front desk to reopen/);
  assert.doesNotMatch(JSON.stringify(h.render()),/check-in is recorded/);
});
test('initially hidden document cannot open a kiosk grant',()=>{
  const h=harness(true);h.render();
  assert.equal(h.clients.length,0);
  assert.equal(elements(h.render()).some(e=>e.type==='form'),false);
});
test('same grant values on parent rerender must not reopen an uncertain submission',async()=>{
  const h=harness();h.render();h.fill('Fictional Visitor');const work=h.submit();
  h.clients[0].finish('unconfirmed');await work;
  assert.match(JSON.stringify(h.render()),/could not confirm/);
  h.update({});assert.equal(h.clients.length,1);
  assert.match(JSON.stringify(h.render()),/could not confirm/);
});
test('grant replacement closes old client and ignores old success',async()=>{
  const h=harness();h.render();h.fill('Fictional Visitor');const work=h.submit();
  assert.doesNotMatch(JSON.stringify(h.render()),/Fictional Visitor/);
  h.update({token:'replacement'});assert.equal(h.clients[0].closed,1);
  h.clients[0].finish('confirmed');await work;
  assert.ok(elements(h.render()).some(e=>e.type==='form'));
  assert.doesNotMatch(JSON.stringify(h.render()),/check-in is recorded/);
});
test('privacy expiry and pagehide discard pending visitor and late response',async()=>{
  for(const kind of ['privacy','pagehide']){
    const h=harness();h.render();h.fill('Fictional Visitor');const work=h.submit();
    if(kind==='privacy')h.privacy().expire();else h.listeners.get('pagehide')();
    h.clients[0].finish('confirmed');await work;
    assert.match(JSON.stringify(h.render()),/front desk to reopen/);
    assert.doesNotMatch(JSON.stringify(h.render()),/Fictional Visitor|check-in is recorded/);
    h.unmount();assert.equal(h.listeners.size,0);assert.equal(h.privacy().stopped,true);
  }
});
test('grant deadline clears draft without waiting for submit or inactivity',()=>{
  const h=harness();h.render();h.fill('Fictional Visitor');
  const expiry=[...h.timers.values()].find(t=>t.ms===99000);assert.ok(expiry);
  expiry.fn();assert.match(JSON.stringify(h.render()),/front desk to reopen/);
  assert.doesNotMatch(JSON.stringify(h.render()),/Fictional Visitor/);
  h.unmount();assert.equal(h.timers.size,0);
});
test('already expired grant never opens an input form or creates a client',()=>{
  const h=harness();h.update({expiresAt:1});
  assert.equal(h.clients.length,0);
  assert.equal(elements(h.render()).some(e=>e.type==='form'),false);
  assert.match(JSON.stringify(h.render()),/front desk to reopen/);
});
