"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import { useEffect, useState } from 'react';
import { getDnsInstructions, startWebsiteDraft, submitWebsite, updateAdminSettings, type Website } from '@/lib/websites';
import { API_BASE } from '@/lib/api';
import { authHeaders } from '@/lib/auth';
import styles from './WebsiteTraffic.module.css';

export function WebsiteDomainSetup({website,onChange}:{website:Website|null;onChange:(site:Website)=>void}) {
 const [domain,setDomain]=useState(website?.admin_settings?.custom_domain||'');
 const [dns,setDns]=useState<Record<string,unknown>|null>(null);
 const [verification,setVerification]=useState<{txt_host:string;txt_value:string|null;ownership_verified:boolean;hosting_active:boolean;hosting_configured:boolean;status?:string;hosting_checked_at?:string;checked_at?:string;message:string}|null>(null);
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const [checkingUntil,setCheckingUntil]=useState(0);
 const [checkTick,setCheckTick]=useState(0);
 useEffect(()=>{setDomain(website?.admin_settings?.custom_domain||'');setCheckingUntil(0)},[website?.id,website?.admin_settings?.custom_domain]);
 useEffect(()=>{
  if(!website||!checkingUntil||verification?.hosting_active)return;
  let active=true;const controller=new AbortController();
  const timer=setTimeout(async()=>{
   if(Date.now()>checkingUntil){setCheckingUntil(0);setNotice('Certificate setup is taking longer than usual. You can check HTTPS again without creating another hosting assignment.');return;}
   try{const response=await fetch(`${API_BASE}/websites/${encodeURIComponent(website.id)}/domain-connection/check_https`,{method:'POST',headers:authHeaders(),signal:controller.signal});const data=await response.json();if(active&&response.ok&&!data.error){setVerification(data);setNotice(data.message);if(data.hosting_active)setCheckingUntil(0)}}catch{}
   if(active)setCheckTick(value=>value+1);
  },10000);
  return()=>{active=false;clearTimeout(timer);controller.abort()};
 },[website?.id,checkingUntil,verification?.hosting_active,checkTick]);
 useEffect(()=>{let active=true;if(website)getDnsInstructions(website.id).then(value=>{if(active)setDns(value)}).catch(()=>{if(active)setNotice('Unable to load DNS instructions. Reopen this tab to try again.')});return()=>{active=false}},[website?.id,website?.admin_settings?.custom_domain]);
 useEffect(()=>{let active=true;setVerification(null);if(website?.admin_settings?.custom_domain)fetch(`${API_BASE}/websites/${encodeURIComponent(website.id)}/domain-connection`,{headers:authHeaders()}).then(r=>r.json()).then(data=>{if(active&&!data.error){setVerification(data);if(data.status==='activating'&&!data.hosting_active)setCheckingUntil(Date.now()+10*60*1000)}}).catch(()=>{});return()=>{active=false}},[website?.id,website?.admin_settings?.custom_domain]);
 if(!website)return <section className={styles.root}><h2>Domain &amp; publish</h2><p>Select your website in My Sites to set up its address. Publishing reviews are below.</p></section>;
 async function checkDomain(action?:'prepare'|'verify'|'activate'|'check_https'){if(!website)return;setBusy(true);setNotice('');try{const response=await fetch(`${API_BASE}/websites/${encodeURIComponent(website.id)}/domain-connection${action?'/'+action:''}`,{method:action?'POST':'GET',headers:authHeaders()});const data=await response.json();if(!response.ok||data.error)throw Error(data.error||'Unable to check domain');setVerification(data);setNotice(data.message);if(action==='activate')setCheckingUntil(Date.now()+10*60*1000);}catch(e){setNotice(e instanceof Error?e.message:'Unable to check domain')}finally{setBusy(false)}}
 const editable=['draft','rejected'].includes(website.status);
 const saved=website.admin_settings?.custom_domain||'';
 const dirty=domain.trim().toLowerCase()!==saved;
 async function act(action:'save'|'draft'|'submit'){
  if(!website)return;setBusy(true);setNotice('');
  try {
   let next:Website;
   if(action==='save')next=await updateAdminSettings(website.id,{custom_domain:domain.trim().toLowerCase()||null});
   else if(action==='draft')next=await startWebsiteDraft(website.id);
   else next=await submitWebsite(website.id);
   onChange(next);setDomain(next.admin_settings?.custom_domain||'');
   setNotice(action==='save'?'Website address saved. Hosting connection is still required.':action==='draft'?'Draft opened. Your published website stays unchanged.':'Submitted for publishing review.');
  }catch(e){setNotice(e instanceof Error?e.message:'Unable to save changes.')}finally{setBusy(false)}
 }
 async function copy(value:string){try{await navigator.clipboard.writeText(value);setNotice('Copied.')}catch{setNotice('Copy unavailable. Select the record text to copy it.')}}
 return <section className={styles.root}>
  <header><div><p>YOUR WEBSITE ADDRESS</p><h2>Domain &amp; publish</h2><span>Connect the address customers will use to find your dealership.</span></div></header>
  <div className={styles.grid}>
   <section className={styles.card}><h3>1. Choose your domain</h3><p>Use a domain you already own, such as www.yourdealership.com.</p>
    <label className={styles.connection}>Website domain<WorkInput aria-label="Website domain" placeholder="www.yourdealership.com" value={domain} disabled={busy||!editable} onChange={e=>setDomain(e.target.value)} spellCheck={false} autoCapitalize="none"/></label>
    {editable?<WorkButton type="submit" disabled={busy||!dirty} onClick={()=>void act('save')}>Save domain</WorkButton>:website.status==='published'?<WorkButton type="submit" disabled={busy} onClick={()=>void act('draft')}>Edit domain in a new draft</WorkButton>:<p>Your website is in review. Domain changes are locked until review is complete.</p>}
    <p className={styles.note}>Enter only the hostname, without https:// or a page path. Saving an address does not connect it.</p>
   </section>
   <section className={styles.card}><h3>Connection status</h3><div className={styles.row}><span>Domain</span><strong>{saved?'Saved':'Not added'}</strong></div><div className={styles.row}><span>DNS verification</span><strong>{verification?.ownership_verified?'Ownership verified':'Not verified'}</strong></div><div className={styles.row}><span>Hosting &amp; HTTPS</span><strong>{verification?.hosting_active?'HTTPS verified':checkingUntil?'Setting up HTTPS':verification?.hosting_configured?'Ready to connect':'Platform setup required'}</strong></div><p>{verification?.hosting_active?'Your approved website is reachable at its custom domain over HTTPS.':verification?.hosting_configured?'Add the DNS records below and approve your website, then select Connect hosting. NXTDeal sets up hosting and automatically checks the HTTPS certificate. This may take a few minutes.':'Automatic hosting is not available yet. Contact NXTDeal to complete the platform connection.'}</p><div className={styles.controls}><WorkButton type="submit" disabled={busy||!!checkingUntil||dirty||!verification?.ownership_verified||!verification?.hosting_configured||website.status!=='published'} onClick={()=>void checkDomain('activate')}>{checkingUntil?'Setting up HTTPS…':'Connect hosting'}</WorkButton><WorkButton type="submit" disabled={busy||dirty||!verification?.ownership_verified||!verification?.hosting_configured} onClick={()=>void checkDomain('check_https')}>Check HTTPS</WorkButton></div>{verification?.hosting_checked_at&&<p>Last hosting check {new Date(verification.hosting_checked_at).toLocaleString()}</p>}</section>
  </div>
  <section className={styles.card} style={{marginBottom:18}}><h3>Verify domain ownership</h3><p>Add a TXT record to prove this domain belongs to your dealership. This does not move your current website or email.</p><div className={styles.controls}><WorkButton type="submit" disabled={busy||!saved||dirty} onClick={()=>void checkDomain('prepare')}>Get ownership record</WorkButton><WorkButton type="submit" disabled={busy||!verification?.txt_value||dirty} onClick={()=>void checkDomain('verify')}>{busy?'Checking…':'Check DNS'}</WorkButton></div>{verification?.txt_value&&<><div className={styles.row}><span>Type</span><strong>TXT</strong></div><div className={styles.row}><span>Name</span><code style={{overflowWrap:'anywhere'}}>{verification.txt_host}</code><WorkButton type="submit" onClick={()=>void copy(verification.txt_host)}>Copy TXT name</WorkButton></div><div className={styles.row} style={{flexWrap:'wrap'}}><span>Value</span><code style={{overflowWrap:'anywhere'}}>{verification.txt_value}</code><WorkButton type="submit" onClick={()=>void copy(verification.txt_value!)}>Copy TXT value</WorkButton></div><p>{verification.checked_at?`Last checked ${new Date(verification.checked_at).toLocaleString()}`:'Add the TXT record, then choose Check DNS.'}</p></>}</section>
  <section className={styles.card}><h3>2. Prepare your DNS records</h3>{saved&&dns?.record_target?<>
   <p>Routing record for <strong>{saved}</strong>. Add this record when you are ready to connect your approved NXTDeal website.</p>
   <div className={styles.row}><span>Type</span><strong>{String(dns.record_type||'CNAME')}</strong></div>
   <div className={styles.row}><span>Host / name (full hostname)</span><code>{saved}</code><WorkButton type="submit" onClick={()=>void copy(saved)}>Copy host</WorkButton></div>
   <div className={styles.row}><span>Points to / target</span><code>{String(dns.record_target)}</code><WorkButton type="submit" onClick={()=>void copy(String(dns.record_target))}>Copy target</WorkButton></div>
   <p>Open DNS settings at your domain provider and enter the supplied record. Some providers expect a relative name such as “www” instead of the full hostname. Leave TTL on Auto or its default.</p>
   <p>For a root domain, your provider may use “@” as the host. Replace conflicting A or AAAA records for this exact hostname; keep your email records unchanged. DNS changes may take time to propagate.</p>
  </>:<p>{saved?'NXTDeal must assign the hosting target before DNS routing records are shown.':'Save your domain above to see its DNS record.'}</p>}</section>
  <section className={styles.card} style={{marginTop:18}}><h3>3. Publish your website</h3><p>Website content: <strong>{website.status.replaceAll('_',' ')}</strong>. Content approval and your custom-domain connection are separate steps.</p>
   {editable?<WorkButton type="submit" disabled={busy||dirty} onClick={()=>void act('submit')}>Submit website for review</WorkButton>:<p>{website.status==='published'?(verification?.hosting_active?'Your approved website is available on its verified custom domain.':'The approved version is published on its app address. Check the domain connection above.'):'An authorized reviewer must approve this version before publication.'}</p>}
   {website.status==='published'&&<a href={`/site/${encodeURIComponent(website.id)}`} target="_blank" rel="noreferrer">View published website ↗</a>}
   {dirty&&<p>Save the domain before submitting.</p>}
  </section>{notice&&<p role="status" className={styles.note}>{notice}</p>}
 </section>;
}
