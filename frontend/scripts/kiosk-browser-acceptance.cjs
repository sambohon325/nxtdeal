// Manual isolated Chromium acceptance. PLAYWRIGHT_MODULE may point to a bundled
// Playwright installation. No package installation, real API or staff session.
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const { webpack } = require('next/dist/compiled/webpack/webpack');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');

(async () => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'nxtdeal-kiosk-browser-'));
  let browser, server, backend, backendExit, rpc;
  try {
    if(process.env.KIOSK_REAL_BACKEND==='1'){
      const backendRoot=path.resolve(root,'../backend');
      const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>['SYSTEMROOT','WINDIR','PATH','TEMP','TMP','HOME','USERPROFILE'].includes(key.toUpperCase())));
      Object.assign(env,{DEALEROS_STORAGE_DIR:path.join(temp,'tenant'),PYTHONPATH:backendRoot,PYTHON_DOTENV_DISABLED:'1'});
      backend=spawn(process.env.KIOSK_PYTHON || path.join(backendRoot,'venv/Scripts/python.exe'),
        [path.join(backendRoot,'tests/kiosk_browser_bridge.py')],{cwd:temp,env,windowsHide:true,stdio:['pipe','pipe','pipe']});
      let id=0;const pending=new Map();
      rpc=(request)=>new Promise((resolve,reject)=>{
        const key=++id;const timer=setTimeout(()=>{pending.delete(key);reject(new Error('Synthetic backend timed out'));},10000);
        pending.set(key,result=>{clearTimeout(timer);resolve(result);});
        backend.stdin.write(JSON.stringify({id:key,...request})+'\n');
      });
      readline.createInterface({input:backend.stdout}).on('line',line=>{
        if(!line.startsWith('KIOSK_RESULT '))return;
        const result=JSON.parse(line.slice(13));pending.get(result.id)?.(result);pending.delete(result.id);
      });
      backend.stderr.on('data',()=>{}); // Never forward auth diagnostics.
      backendExit=new Promise(resolve=>backend.once('exit',resolve));
      backend.on('error',()=>{});
    }
    await fs.writeFile(path.join(temp, 'entry.tsx'), `
      import React from 'react';
      import {createRoot} from 'react-dom/client';
      import {KioskStation} from '@/components/kiosk/KioskStation';
      createRoot(document.getElementById('root')!).render(
        <React.StrictMode><KioskStation apiOrigin={location.origin} deviceId="fictional-lobby" /></React.StrictMode>);
    `);
    await fs.writeFile(path.join(temp, 'loader.cjs'), `
      const ts=require(${JSON.stringify(require.resolve('typescript'))});
      module.exports=function(source){return ts.transpileModule(source,{compilerOptions:{
        module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX
      }}).outputText};
    `);
    await new Promise((resolve, reject) => {
      const compiler = webpack({mode:'development',devtool:false,context:root,
        entry:path.join(temp,'entry.tsx'),output:{path:temp,filename:'bundle.js'},
        resolve:{extensions:['.tsx','.ts','.js'],alias:{'@':root},modules:[path.join(root,'node_modules')]},
        module:{rules:[{test:/\.tsx?$/,exclude:/node_modules/,use:path.join(temp,'loader.cjs')}]},
      });
      compiler.run((error, stats) => compiler.close(() => error || stats.hasErrors()
        ? reject(error || new Error(stats.toString({all:false,errors:true}))) : resolve()));
    });
    const bundle = await fs.readFile(path.join(temp,'bundle.js'));
    const calls=[];
    server=http.createServer(async (req,res) => {
      res.setHeader('Cache-Control','no-store');
      if(req.url==='/bundle.js'){res.setHeader('Content-Type','application/javascript');res.end(bundle);return;}
      if(req.method==='POST'){
        const chunks=[];for await(const chunk of req)chunks.push(chunk);
        const body=JSON.parse(Buffer.concat(chunks));calls.push(req.url);
        if(rpc){
          try {
            const result=await rpc({path:req.url,body,headers:{authorization:req.headers.authorization || ''}});
            res.writeHead(result.status,{'Content-Type':'application/json'});res.end(JSON.stringify(result.data));
          } catch {res.writeHead(500,{'Content-Type':'application/json'});res.end('{"error":"Synthetic backend unavailable"}');}
          return;
        }
        let data,status=200;
        if(req.url==='/auth/login') data=body.password==='fictional-password'
          ?{mfa_required:true,mfa_challenge_token:'fictional-challenge'}:{error:'Invalid credentials'};
        else if(req.url==='/auth/mfa/verify')data=body.code==='123456'
          ?{token:'fictional-admin',role:'ADMIN',must_change_password:false}:{error:'Invalid code'};
        else if(req.url==='/kiosk/enroll'){status=201;data={token:'kiosk_'+'a'.repeat(43),expires_at:Date.now()/1000+600,action:'lobby:checkin:create'};}
        else if(req.url==='/kiosk/checkin')data={status:'checked_in',receipt:body.request_id};
        else if(req.url==='/kiosk/revoke')data={status:'revoked'};
        else {status=404;data={error:'Unknown synthetic endpoint'};}
        res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));return;
      }
      res.setHeader('Content-Type','text/html');
      res.end('<!doctype html><html><head><title>Synthetic kiosk acceptance</title></head><body><div id="root"></div><script src="/bundle.js"></script></body></html>');
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const origin=`http://127.0.0.1:${server.address().port}`;
    browser=await chromium.launch({headless:true, ...(process.env.KIOSK_BROWSER_CHANNEL ? {channel:process.env.KIOSK_BROWSER_CHANNEL} : {})});
    const context=await browser.newContext();
    await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
    page.setDefaultTimeout(5000);
    await page.goto(origin);
    const visible=text=>page.getByText(text,{exact:true}).waitFor({state:'visible'});
    async function password(value='fictional-password'){
      await page.getByLabel('Employee ID or email').fill('SYN-ADMIN');
      await page.getByLabel('Password',{exact:true}).fill(value);
      await page.getByRole('button',{name:'Continue',exact:true}).click();
    }
    async function mfa(){
      const code=rpc?(await rpc({path:'__fixture_totp'})).data.code:'123456';
      await page.getByLabel('Authenticator or recovery code').fill(code);
      await page.getByRole('button',{name:'Continue',exact:true}).click();
    }
    await page.getByRole('button',{name:'Start check-in',exact:true}).click();
    await password('wrong');await visible('Sign-in could not be completed. An administrator can try again.');
    await page.getByRole('button',{name:'Start check-in',exact:true}).click();
    await password();await mfa();await page.getByLabel('Name',{exact:true}).fill('Fictional Browser Visitor');
    await page.getByRole('button',{name:'Check in',exact:true}).click();
    await visible('Thank you. Your check-in is recorded.');
    await page.getByRole('button',{name:'Stop check-in and sign in',exact:true}).click();
    assert.equal(await page.getByLabel('Name',{exact:true}).count(),0);
    await password();await mfa();await visible('Station access was revoked. This screen remains closed.');
    assert.equal(calls.filter(x=>x==='/auth/login').length,3);
    assert.equal(calls.filter(x=>x==='/auth/mfa/verify').length,2);
    assert.equal(calls.filter(x=>x==='/kiosk/checkin').length,1);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    await page.reload();await page.getByRole('button',{name:'Start check-in',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Name',{exact:true}).count(),0);
    // Cancel at the MFA prompt: no verification or enrollment may follow.
    const beforeCancel=calls.length;
    await page.getByRole('button',{name:'Start check-in',exact:true}).click();
    await password();await page.getByLabel('Authenticator or recovery code').waitFor();
    await page.getByRole('button',{name:'Cancel sign-in',exact:true}).click();
    await visible('Sign-in could not be completed. An administrator can try again.');
    assert.deepEqual(calls.slice(beforeCancel),['/auth/login']);
    // Real navigation/pagehide and browser Back must not recover a password draft.
    await page.getByRole('button',{name:'Start check-in',exact:true}).click();
    await page.getByLabel('Password',{exact:true}).fill('fictional-private-draft');
    await page.goto('about:blank');await page.goBack();
    await page.getByRole('heading',{name:'Reception station',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Name',{exact:true}).count(),0);
    assert.equal(await page.locator('input').evaluateAll(nodes=>nodes.some(n=>n.value==='fictional-private-draft')),false);
    await page.reload();
    await page.getByRole('button',{name:'Start check-in',exact:true}).click();
    await password();await mfa();await page.getByLabel('Name',{exact:true}).waitFor();
    // Revoke really succeeds, but lose its confirmation: keep the UI closed and
    // do not retry automatically, even though the isolated backend has revoked it.
    await page.route(origin+'/kiosk/revoke',async route=>{
      const reply=await route.fetch();assert.equal(reply.status(),200);
      await route.fulfill({status:503,json:{error:'synthetic_lost_confirmation'}});
    });
    await page.getByRole('button',{name:'Stop check-in and sign in',exact:true}).click();
    await password();await mfa();
    await visible('We could not confirm this change. Keep this station closed and ask an administrator to review it.');
    assert.equal(await page.getByLabel('Name',{exact:true}).count(),0);
    assert.equal(await page.getByRole('button').count(),0);
    assert.equal(calls.filter(x=>x==='/kiosk/revoke').length,2);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    assert.deepEqual(errors,[]);
    if(rpc){
      const evidence=(await rpc({path:'__fixture_evidence'})).data;
      assert.deepEqual(evidence,{leads:1,assigned:['SYN-REP'],active_grants:0});
    }
    console.log('PASS: Chromium StrictMode enrollment, denied login, MFA, visitor check-in, fresh-auth stop, empty storage/reload, MFA cancellation, navigation/Back privacy and lost-revoke confirmation. '+(rpc?'Real isolated ASGI auth/kiosk, real TOTP, ledger and journal.':'Fake API only.'));
  } finally {
    await browser?.close();
    if(server)await new Promise(resolve=>server.close(resolve));
    if(backend){
      backend.stdin.end();
      const timer=setTimeout(()=>backend.kill(),2000);
      await backendExit;
      clearTimeout(timer);
    }
    const tenant=path.resolve(temp,'tenant');
    assert.equal(path.dirname(tenant),temp);
    assert.equal(path.dirname(temp),path.resolve(os.tmpdir()));
    assert.ok(path.basename(temp).startsWith('nxtdeal-kiosk-browser-'));
    await fs.rm(tenant,{recursive:true,force:true}); // Verified disposable fixture only.
    // Exact generated files only; no recursive workspace deletion.
    for(const file of ['entry.tsx','loader.cjs','bundle.js'])await fs.rm(path.join(temp,file),{force:true});
    await fs.rmdir(temp);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
