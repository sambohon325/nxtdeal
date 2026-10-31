import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function load(name){
  const source=ts.transpileModule(fs.readFileSync(new URL(`../lib/${name}.ts`,import.meta.url),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020},
  }).outputText;
  const scope={exports:{},URL,AbortController,Date,setTimeout,clearTimeout};
  vm.runInNewContext(source,scope);return scope.exports;
}
const {createKioskSignIn}=load('kioskSignIn');
const {createKioskEnrollment}=load('kioskEnrollment');
const origin='https://synthetic.example.test';
const success={role:'ADMIN',token:'fictional-staff',must_change_password:false};
const response=data=>({ok:true,status:200,json:async()=>data});
const credentials=async()=>({employeeId:' SYN-ADMIN ',password:'fictional-password'});

test('composed enrollment and revoke each require new password and MFA flow',async()=>{
  const calls=[];let passwords=0,codes=0;
  const send=async(url,init)=>{
    const path=new URL(url).pathname;calls.push({path,init});
    if(path==='/auth/login')return response({mfa_required:true,mfa_challenge_token:'fictional-challenge'});
    if(path==='/auth/mfa/verify')return response(success);
    if(path==='/kiosk/enroll')return {...response({token:'kiosk_'+'a'.repeat(43),action:'lobby:checkin:create',expires_at:Date.now()/1000+600}),status:201};
    return response({status:'revoked'});
  };
  const auth=createKioskSignIn(origin,{credentials:async()=>{passwords++;return credentials();},mfa:async()=>{codes++;return '123456';}},send);
  const client=createKioskEnrollment(origin,auth,send);
  assert.equal((await client.enroll('lobby')).status,'enrolled');
  assert.equal((await client.revoke('lobby')).status,'revoked');
  assert.equal(passwords,2);assert.equal(codes,2);
  assert.deepEqual(calls.map(c=>c.path),['/auth/login','/auth/mfa/verify','/kiosk/enroll','/auth/login','/auth/mfa/verify','/kiosk/revoke']);
  for(const {path,init} of calls){
    assert.equal(init.credentials,'omit');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');
    if(path.startsWith('/auth/'))assert.equal(init.headers.Authorization,undefined);
    else {assert.equal(init.headers.Authorization,'Bearer fictional-staff');assert.equal(init.body,'{"device_id":"lobby"}');}
  }
});

test('non-MFA admin can authenticate; password change, sales and errors fail closed',async()=>{
  for(const [data,expected] of [[success,'fictional-staff'],[{...success,must_change_password:true},null],[{...success,role:'SALES'},null],[{error:'private diagnostic'},null]]){
    const auth=createKioskSignIn(origin,{credentials,mfa:()=>assert.fail('No MFA prompt')},async()=>response(data));
    assert.equal(await auth(new AbortController().signal),expected);
  }
});

test('closing while waiting for MFA never sends code or management request',async()=>{
  let resolveCode;const calls=[];
  const send=async(url)=>{calls.push(url);return response({mfa_required:true,mfa_challenge_token:'fixture'});};
  const auth=createKioskSignIn(origin,{credentials,mfa:()=>new Promise(r=>resolveCode=r)},send);
  const client=createKioskEnrollment(origin,auth,send);
  const work=client.enroll('lobby');await new Promise(r=>setImmediate(r));
  client.close();assert.equal((await work).status,'closed');
  resolveCode('123456');await new Promise(r=>setImmediate(r));
  assert.deepEqual(calls,[origin+'/auth/login']);
});

test('late password response after abort never advances to MFA',async()=>{
  let finish;const controller=new AbortController();
  const auth=createKioskSignIn(origin,{credentials,mfa:()=>assert.fail('Aborted')},()=>new Promise(r=>finish=r));
  const work=auth(controller.signal);await new Promise(r=>setImmediate(r));controller.abort();
  finish(response({mfa_required:true,mfa_challenge_token:'fixture'}));assert.equal(await work,null);
});
