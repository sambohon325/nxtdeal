import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const manifest=path.join(root,'frontend/lib/help-review.json');
// UI and workflow changes require an explicit tutorial review before CI passes.
const roots=['frontend/components','frontend/lib','backend/core/menu_catalog.py','backend/core/workflow_catalog.py'];
function files(p){if(!fs.existsSync(p))return [];return fs.statSync(p).isDirectory()?fs.readdirSync(p).sort().flatMap(n=>files(path.join(p,n))):/\.(tsx?|py)$/.test(p)&&!/[\\/]helpContent\.ts$/.test(p)?[p]:[];}
const hash=crypto.createHash('sha256');
for(const name of roots.flatMap(p=>files(path.join(root,p))).map(file=>path.relative(root,file).replaceAll('\\','/')).sort()){hash.update(name);hash.update(fs.readFileSync(path.join(root,name),'utf8').replaceAll('\r\n','\n'));}
const fingerprint=hash.digest('hex');
if(process.argv.includes('--review')){
 const note=process.argv[process.argv.indexOf('--review')+1];if(!note||note.startsWith('--'))throw Error('Supply a meaningful review note after --review.');
 fs.writeFileSync(manifest,JSON.stringify({fingerprint,reviewedAt:new Date().toISOString().slice(0,10),note},null,2)+'\n');
}else{
 const saved=JSON.parse(fs.readFileSync(manifest,'utf8'));
 if(saved.fingerprint!==fingerprint)throw Error('Help review required: review affected tutorials in frontend/lib/helpContent.ts, then run node frontend/scripts/check-help-review.mjs --review "Describe reviewed workflows and guide changes" and commit help-review.json.');
 console.log('Knowledge-base review matches current workflow sources.');
}
