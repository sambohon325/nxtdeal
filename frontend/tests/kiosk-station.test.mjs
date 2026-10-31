import {workControls} from './work-controls-stub.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsx from 'react/jsx-runtime';
const source=ts.transpileModule(fs.readFileSync(new URL('../components/kiosk/KioskStation.tsx',import.meta.url),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX},
}).outputText;
const elements=e=>!e||typeof e!=='object'?[]:[e,...[e.props?.children].flat(Infinity).flatMap(elements)];
const tick=()=>new Promise(r=>setImmediate(r));
function harness(){
  const state=[],effects=[],listeners=new Map(),calls=[];let cursor=0,index=0,revocation='revoked';
  const hook=initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=v];};
  const document={visibilityState:'visible',addEventListener:(k,v)=>listeners.set(k,v),removeEventListener:k=>listeners.delete(k)};
  const Lobby=()=>null;
  const scope={exports:{},document,window:{addEventListener:(k,v)=>listeners.set(k,v),removeEventListener:k=>listeners.delete(k)},require:name=>{if(name.endsWith('/WorkspaceUi'))return workControls;
    if(name==='react/jsx-runtime')return jsx;
    if(name==='react')return{useState:hook,useRef:v=>hook({current:v})[0],useEffect:(fn,deps)=>{
      const i=index++,old=effects[i];if(!old||deps.some((v,j)=>v!==old.deps[j]))effects[i]={fn,deps,pending:true,cleanup:old?.cleanup};
    }};
    if(name==='./RestrictedLobby')return{RestrictedLobby:Lobby};
    if(name==='@/lib/kioskSignIn')return{createKioskSignIn:(_origin,prompts)=>async signal=>{
      const credentials=await prompts.credentials(signal);if(!credentials)return null;
      calls.push('password');const code=await prompts.mfa(signal);if(!code)return null;calls.push('mfa');return 'fictional';
    }};
    if(name==='@/lib/kioskEnrollment')return{createKioskEnrollment:(_origin,auth)=>{
      const controller=new AbortController();
      const run=async revoke=>{calls.push(revoke?'revoke':'enroll');if(!await auth(controller.signal))return{status:'denied'};
        return revoke?{status:revocation}:{status:'enrolled',grant:{token:'fixture',deviceId:'lobby',expiresAt:9999999999,apiOrigin:'https://example.test'}};};
      return{enroll:()=>run(false),revoke:()=>run(true),close:()=>controller.abort()};
    }};throw Error(name);
  }};
  vm.runInNewContext(source,scope);
  function render(){cursor=0;index=0;const tree=scope.exports.KioskStation({apiOrigin:'https://example.test',deviceId:'lobby'});
    const pending=effects.filter(e=>e.pending);if(pending.length){for(const e of pending){e.cleanup?.();e.cleanup=e.fn();e.pending=false;}return render();}return tree;}
  return{render,calls,lobby:()=>elements(render()).some(e=>e.type===Lobby),
    click:label=>elements(render()).find(e=>e.type==='button'&&e.props.children===label).props.onClick(),
    fill:values=>elements(render()).filter(e=>e.type==='input').forEach((e,i)=>e.props.onChange({target:{value:values[i]}})),
    submit:()=>elements(render()).find(e=>e.type==='form').props.onSubmit({preventDefault(){}}),
    hide:()=>{document.visibilityState='hidden';listeners.get('visibilitychange')();},
    uncertain:()=>revocation='unconfirmed',unmount:()=>effects.forEach(e=>e.cleanup?.())};
}
async function signIn(h){h.fill(['fixture-admin','fixture-password']);h.submit();await tick();h.fill(['123456']);h.submit();await tick();}
test('enroll prompts for password/MFA; exit removes lobby before fresh sign-in',async()=>{
  const h=harness();h.render();h.click('Start check-in');await signIn(h);assert.equal(h.lobby(),true);
  h.click('Stop check-in and sign in');assert.equal(h.lobby(),false);
  assert.equal(JSON.stringify(h.render()).includes('fixture-password'),false);
  await signIn(h);assert.match(JSON.stringify(h.render()),/access was revoked/);
  assert.deepEqual(h.calls,['enroll','password','mfa','revoke','password','mfa']);h.unmount();
});
test('hiding during password entry clears input and prevents later opening',async()=>{
  const h=harness();h.render();h.click('Start check-in');h.fill(['fixture','private-draft']);h.hide();await tick();
  assert.equal(h.lobby(),false);assert.doesNotMatch(JSON.stringify(h.render()),/private-draft/);
  assert.match(JSON.stringify(h.render()),/Station closed/);assert.deepEqual(h.calls,['enroll']);h.unmount();
});
test('uncertain revocation keeps lobby absent and does not offer retry',async()=>{
  const h=harness();h.render();h.click('Start check-in');await signIn(h);h.uncertain();
  h.click('Stop check-in and sign in');await signIn(h);
  assert.equal(h.lobby(),false);assert.match(JSON.stringify(h.render()),/could not confirm/);
  assert.equal(elements(h.render()).some(e=>e.type==='button'),false);h.unmount();
});
