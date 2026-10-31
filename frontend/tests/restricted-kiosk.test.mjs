import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../lib/restrictedKiosk.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const grant = { token: 'kiosk_' + 'a'.repeat(43), deviceId: 'lobby', expiresAt: 9999999999, apiOrigin: 'https://synthetic.example.test' };
const fields = {name:'Fictional Visitor',phone:'',reason:''};
function create(send, overrides={}, runtime={}) {
  let id=0;
  const scope = {exports:{}, URL, AbortController, Date, setTimeout, clearTimeout, crypto:{randomUUID:()=>`request-${++id}`}, fetch:send, ...runtime};
  vm.runInNewContext(source, scope);
  return scope.exports.createRestrictedKiosk({...grant,...overrides},send);
}
function ok(init) { return {ok:true,status:200,json:async()=>({status:'checked_in',receipt:JSON.parse(init.body).request_id})}; }

for (const stall of ['headers', 'body']) test(`stalled ${stall} times out without retry or accepting late success`,async()=>{
  const timers=new Map();let finish,signal,calls=0;
  const client=create(async(_url,init)=>{
    calls++;signal=init.signal;
    if(stall==='headers')return new Promise(resolve=>finish=()=>resolve(ok(init)));
    return {ok:true,status:200,json:()=>new Promise(resolve=>finish=()=>resolve({status:'checked_in',receipt:JSON.parse(init.body).request_id}))};
  },{}, {setTimeout:(fn,ms)=>{timers.set(1,{fn,ms});return 1;},clearTimeout:id=>timers.delete(id)});
  const work=client.submit(fields);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(timers.get(1)?.ms,15000);
  timers.get(1).fn();
  assert.equal(await work,'unconfirmed');assert.equal(signal.aborted,true);
  assert.equal(timers.size,0);
  finish();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(await client.submit(fields),'unconfirmed');assert.equal(calls,1);
});

test('sends only kiosk bearer, omits cookies, rejects redirects and whitelists fields', async()=>{
  let recorded;
  const client=create(async(url,init)=>{recorded={url,init};return ok(init);});
  assert.equal(await client.submit({...fields, role:'ADMIN',tenant_id:'other'}),'confirmed');
  assert.equal(recorded.url,'https://synthetic.example.test/kiosk/checkin');
  assert.equal(recorded.init.credentials,'omit');assert.equal(recorded.init.redirect,'error');
  assert.equal(recorded.init.cache,'no-store');assert.equal(recorded.init.headers.Authorization,`Bearer ${grant.token}`);
  assert.deepEqual(Object.keys(JSON.parse(recorded.init.body)).sort(),['device_id','name','phone','reason','request_id']);
});

test('duplicate click cannot send twice; next confirmed visitor uses a new request ID',async()=>{
  let finish; const requests=[];
  const client=create((url,init)=>{requests.push(init);return new Promise(r=>finish=()=>r(ok(init)));});
  const first=client.submit(fields);assert.equal(await client.submit(fields),'busy');
  finish();assert.equal(await first,'confirmed');
  const second=client.submit(fields);finish();await second;
  assert.notEqual(JSON.parse(requests[0].body).request_id,JSON.parse(requests[1].body).request_id);
});

test('unknown write blocks automatic retry and never exposes private response errors',async()=>{
  for(const result of ['network','server','mismatch']) {
    let calls=0;
    const client=create(async()=>{calls++;if(result==='network')throw Error('private details');
      return {ok:result==='mismatch',status:result==='server'?503:200,json:async()=>({status:'checked_in',receipt:'wrong',error:'private'})};});
    assert.equal(await client.submit(fields),'unconfirmed');
    assert.equal(await client.submit(fields),'unconfirmed');assert.equal(calls,1);
  }
});

test('close aborts request and suppresses late success even if transport ignores abort',async()=>{
  let finish, signal;
  const client=create((url,init)=>{signal=init.signal;return new Promise(r=>finish=()=>r(ok(init)));});
  const pending=client.submit(fields);client.close();assert.equal(signal.aborted,true);
  finish();assert.equal(await pending,'closed');assert.equal(await client.submit(fields),'closed');
});

test('auth rejection and expired grant require reopening rather than retry',async()=>{
  const client=create(async()=>({status:401,ok:false}));
  assert.equal(await client.submit(fields),'closed');
  assert.equal(await client.submit(fields),'closed');
  const expired=create(()=>{throw Error('must not send');},{expiresAt:1});
  assert.equal(await expired.submit(fields),'closed');
});

test('rejects insecure remote origins, URL secrets and staff-shaped tokens',()=>{
  for(const apiOrigin of ['http://remote.example.test','https://user:pass@example.test','https://example.test?token=secret','https://example.test/staff']) {
    assert.throws(()=>create(()=>{}, {apiOrigin}));
  }
  assert.throws(()=>create(()=>{}, {token:'staff.signed-token'}));
  assert.doesNotThrow(()=>create(()=>{}, {apiOrigin:'http://127.0.0.1:8317'}));
});
