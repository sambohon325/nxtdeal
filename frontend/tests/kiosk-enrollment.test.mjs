import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(fs.readFileSync(new URL('../lib/kioskEnrollment.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
function create(auth, send, runtime={}) {
  const scope={exports:{},URL,AbortController,Date,setTimeout,clearTimeout,...runtime};
  vm.runInNewContext(source,scope);
  return scope.exports.createKioskEnrollment('https://synthetic.example.test',auth,send);
}
const enrolled=()=>({status:201,json:async()=>({token:'kiosk_'+'a'.repeat(43),action:'lobby:checkin:create',expires_at:Date.now()/1000+600})});

test('enrollment and revocation request separate authentication and never return staff tokens',async()=>{
  let auths=0;const calls=[];
  const client=create(async()=>`staff-${++auths}`,async(url,init)=>{
    calls.push({url,init});return url.endsWith('/revoke')?{status:200,json:async()=>({status:'revoked'})}:enrolled();
  });
  const first=await client.enroll(' lobby ');
  assert.equal(first.status,'enrolled');assert.equal(first.grant.deviceId,'lobby');
  assert.equal(first.grant.apiOrigin,'https://synthetic.example.test');
  assert.equal(await client.revoke('lobby').then(x=>x.status),'revoked');
  assert.equal(auths,2);assert.equal(JSON.stringify(first).includes('staff-'),false);
  for (const [i,{init}] of calls.entries()) {
    assert.equal(init.headers.Authorization,`Bearer staff-${i+1}`);
    assert.equal(init.credentials,'omit');assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');
    assert.equal(init.body,'{"device_id":"lobby"}');
  }
});

test('closing during sign-in prevents late token from sending any management request',async()=>{
  let finish,calls=0;
  const client=create(()=>new Promise(r=>finish=r),async()=>{calls++;return enrolled();});
  const work=client.enroll('lobby');
  assert.equal((await client.enroll('lobby')).status,'busy');
  client.close();assert.equal((await work).status,'closed');
  finish('late-staff');await new Promise(r=>setImmediate(r));assert.equal(calls,0);
});

for(const stall of ['headers','body']) test(`stalled ${stall} blocks retry and ignores late grant`,async()=>{
  const timers=new Map();let finish,calls=0,signal;
  const client=create(async()=> 'staff',async(url,init)=>{
    calls++;signal=init.signal;
    if(stall==='headers')return new Promise(r=>finish=()=>r(enrolled()));
    return {status:201,json:()=>new Promise(r=>finish=async()=>r(await enrolled().json()))};
  },{setTimeout:(fn,ms)=>{timers.set(ms,fn);return ms;},clearTimeout:id=>timers.delete(id)});
  const work=client.enroll('lobby');await new Promise(r=>setImmediate(r));
  assert.equal(timers.has(120000),false);timers.get(15000)();
  assert.equal((await work).status,'unconfirmed');assert.equal(signal.aborted,true);
  finish();await new Promise(r=>setImmediate(r));
  assert.equal((await client.enroll('lobby')).status,'unconfirmed');assert.equal(calls,1);
  assert.equal(timers.size,0);
});

test('invalid capability response never becomes a grant',async()=>{
  for(const patch of [{action:'staff:admin'},{token:'staff-token'},{expires_at:0},{expires_at:Infinity}]){
    const client=create(async()=> 'staff',async()=>({status:201,json:async()=>({...await enrolled().json(),...patch})}));
    assert.equal((await client.enroll('lobby')).status,'unconfirmed');
  }
});

test('authentication denial and non-admin rejection cannot enroll',async()=>{
  for(const token of [null,'kiosk_'+'a'.repeat(43)]){
    const client=create(async()=>token,()=>assert.fail('No request allowed'));
    assert.equal((await client.enroll('lobby')).status,'denied');
  }
  const client=create(async()=> 'staff',async()=>({status:403}));
  assert.equal((await client.enroll('lobby')).status,'denied');
});
