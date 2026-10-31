import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../lib/auth.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const settle = () => new Promise(resolve => setImmediate(resolve));
const verified = {employee_id:'SYN-1',role:'SALES',must_change_password:false,allowed_dashboards:['pipeline']};
function client(origin, storage = new Map(), reply = async () => ({ok:true,json:async()=>verified})) {
  const listeners=new Set();let state=null,effect,reloads=0;const redirects=[];
  const localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  const scope = {
    exports: {}, window: {localStorage,location:{reload:()=>reloads++},addEventListener:(_,fn)=>listeners.add(fn),removeEventListener:(_,fn)=>listeners.delete(fn)},
    localStorage, AbortController, fetch: reply,
    require: name => {
      if (name === 'react') return {useState:()=>[state,value=>{state=value;}],useEffect:fn=>{effect=fn;}};
      if (name === 'next/navigation') return {useRouter:()=>({push:path=>redirects.push(path),replace:path=>redirects.push(path)})};
      if (name === '@/lib/api') return { API_BASE: origin };
      if (name === './canonicalApiUrl') return { canonicalApiUrl: value => value.replace(/\/$/, '') };
      throw Error(name);
    },
  };
  vm.runInNewContext(source, scope);
  return { api: scope.exports, storage, mount:()=>effect(),state:()=>state,reloads:()=>reloads,redirects,
    event:event=>listeners.forEach(fn=>fn({storageArea:localStorage,...event})),listeners:()=>listeners.size };
}
const fictional = { token: 'fictional-staff-token', employeeId: 'SYN-1', role: 'SALES' };

test('staff credentials are sent only to the API origin they were saved for', () => {
  const first = client('https://one.example.test');
  first.api.saveSession(fictional);
  assert.equal(first.api.authHeaders().Authorization, 'Bearer fictional-staff-token');
  const second = client('https://two.example.test', first.storage);
  assert.equal(second.api.getSession(), null);
  assert.equal(second.api.authHeaders().Authorization, undefined);
  // A stale tab must also refuse the newly saved second tenant token.
  second.api.saveSession({ ...fictional, token: 'fictional-second-token' });
  assert.equal(first.api.authHeaders().Authorization, undefined);
  assert.equal(second.api.authHeaders().Authorization, 'Bearer fictional-second-token');
});

test('a resolved tenant login can save its new origin before the required reload', () => {
  const old = client('https://one.example.test');
  old.api.saveSession({ ...fictional, apiBaseUrl: 'https://two.example.test/' });
  assert.equal(old.api.authHeaders().Authorization, undefined);
  const reloaded = client('https://two.example.test', old.storage);
  assert.equal(reloaded.api.authHeaders().Authorization, 'Bearer fictional-staff-token');
});

test('legacy unbound, malformed and empty-token sessions fail closed', () => {
  const h = client('https://one.example.test');
  for (const value of [JSON.stringify(fictional), '{', 'null', JSON.stringify({ ...fictional, token: '', apiBaseUrl: 'https://one.example.test' })]) {
    h.storage.set('dealeros_session', value);
    assert.equal(h.api.getSession(), null);
    assert.equal(h.api.authHeaders().Authorization, undefined);
  }
});

test('protected-page guard hides old content and reloads once for logout, replacement or tenant change',async()=>{
  for(const key of ['dealeros_session','dealeros_tenant_api',null]) {
    const h=client('https://one.example.test');h.api.saveSession(fictional);
    h.api.useRequireAuth();const cleanup=h.mount();await settle();assert.equal(h.state().employeeId,'SYN-1');
    h.event({key,oldValue:'old',newValue:null});assert.equal(h.state(),null);assert.equal(h.reloads(),1);
    h.event({key,oldValue:'old',newValue:'new'});assert.equal(h.reloads(),1);
    cleanup();assert.equal(h.listeners(),0);
  }
});
test('appearance, unchanged values and sessionStorage events leave a protected view intact',async()=>{
  const h=client('https://one.example.test');h.api.saveSession(fictional);h.api.useRequireAuth();const cleanup=h.mount();await settle();
  h.event({key:'appearance',oldValue:'dark',newValue:'light'});
  h.event({key:'dealeros_session',oldValue:'same',newValue:'same'});
  h.event({key:'dealeros_session',oldValue:'old',newValue:null,storageArea:{}});
  assert.equal(h.state().employeeId,'SYN-1');assert.equal(h.reloads(),0);cleanup();
});
test('protected-page guard still redirects anonymous and unauthorized users without exposing a session',async()=>{
  const anonymous=client('https://one.example.test');anonymous.api.useRequireAuth();anonymous.mount();
  assert.deepEqual(anonymous.redirects,['/']);assert.equal(anonymous.state(),null);
  const sales=client('https://one.example.test');sales.api.saveSession(fictional);sales.api.useRequireAuth('ADMIN');sales.mount();await settle();
  assert.deepEqual(sales.redirects,['/workspace']);assert.equal(sales.state(),null);
});


test('temporary-password sessions redirect to recovery without exposing protected content',async()=>{
  const h=client('https://one.example.test',new Map(),async()=>({ok:true,json:async()=>({...verified,must_change_password:true})}));
  h.api.saveSession(fictional);h.api.useRequireAuth();const cleanup=h.mount();
  assert.equal(h.state(),null);await settle();
  assert.equal(h.state(),null);assert.deepEqual(h.redirects,['/change-password']);
  assert.equal(h.api.getSession().token,fictional.token);cleanup();
});
test('revoked, malformed, mismatched, redirect and unreachable verification never expose content',async()=>{
  for(const reply of [
    async()=>({ok:false,json:async()=>verified}),
    async()=>({ok:true,json:async()=>({error:'Invalid or expired token'})}),
    async()=>({ok:true,json:async()=>({...verified,employee_id:'SYN-OTHER'})}),
    async()=>({ok:true,json:async()=>({...verified,must_change_password:undefined})}),
    async()=>{throw Error('Network or redirect rejected');},
  ]){
    const h=client('https://one.example.test',new Map(),reply);h.api.saveSession(fictional);
    h.api.useRequireAuth();const cleanup=h.mount();await settle();
    assert.equal(h.state(),null);assert.deepEqual(h.redirects,['/']);cleanup();
  }
});
test('verification is bound to origin and late responses cannot resurrect a replaced session',async()=>{
  let finish,request;
  const h=client('https://one.example.test',new Map(),(url,options)=>{request={url,options};return new Promise(resolve=>{finish=resolve;});});
  h.api.saveSession(fictional);h.api.useRequireAuth();const cleanup=h.mount();
  assert.equal(request.url,'https://one.example.test/auth/whoami');
  assert.equal(request.options.redirect,'error');assert.equal(request.options.cache,'no-store');
  h.event({key:'dealeros_session',oldValue:'old',newValue:'new'});
  finish({ok:true,json:async()=>verified});await settle();
  assert.equal(h.state(),null);assert.equal(request.options.signal.aborted,true);cleanup();
});
test('role checks use the verified account instead of browser claims',async()=>{
  const h=client('https://one.example.test');h.api.saveSession({...fictional,role:'ADMIN'});
  h.api.useRequireAuth('ADMIN');const cleanup=h.mount();await settle();
  assert.equal(h.state(),null);assert.deepEqual(h.redirects,['/workspace']);cleanup();
});
