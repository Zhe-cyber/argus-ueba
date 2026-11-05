import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui='http://127.0.0.1:3011',api='http://127.0.0.1:8015';
const out='data/live/workspace-case-preview-20261030-v1/browser';
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();let blocked=0;const errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/*',route=>{
 const request=route.request();
 if(request.method()!=='GET'||![ui,api].includes(new URL(request.url()).origin)){blocked++;return route.abort();}
 return route.continue();
});
async function visibleMasked(){
 const text=await page.locator('main').innerText();
 assert.equal(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(text),false,'Visible email escaped masking');
 assert.equal(/\b\d{12}\b/.test(text),false,'Visible account id escaped masking');
 assert.equal(/acct_[0-9a-f]{64}/.test(text),false,'Visible internal account key escaped masking');
}
try{
 const before=await(await context.request.get(api+'/findings?limit=100')).json();
 const finding=before.findings.find(row=>row.alert_type==='anomalous_behavior');assert.ok(finding);
 await page.goto(ui+'/workspace?finding='+finding.id,{waitUntil:'networkidle'});
 await page.getByRole('dialog',{name:'Finding #'+finding.id}).waitFor();
 await page.getByText('Mon–Fri 07:00–19:00 UTC (weekends outside window)',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Close',exact:true}).click();
 await page.getByLabel('Account context',{exact:true}).selectOption('service_or_workload');
 await page.waitForURL('**entity_context=service_or_workload*');
 await page.getByRole('button',{name:/Review #/}).first().waitFor();
 const service=await(await context.request.get(api+'/findings?entity_context=service_or_workload')).json();
 assert.ok(service.findings.length);
 assert.ok(service.findings.every(row=>row.entity_context==='service_or_workload'));
 await page.getByRole('button',{name:'Presentation mode: off',exact:true}).click();
 await page.getByRole('button',{name:'Presentation mode: on (read-only)',exact:true}).waitFor();
 await page.getByRole('button',{name:/Review #/}).first().waitFor();
 await visibleMasked();
 await page.screenshot({path:out+'/queue-reviewed-masked.png',fullPage:false});
 await page.goto(ui+'/entities?tab=people',{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'Inspect',exact:true}).first().click();
 await page.getByText('[email hidden]',{exact:true}).first().waitFor();
 await visibleMasked();
 const cases=(await(await context.request.get(api+'/cases?limit=100')).json()).cases;
 await page.goto(ui+'/cases/'+cases[0].id,{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:'Evidence timeline',exact:true}).waitFor();
 await page.locator('details').evaluateAll(nodes=>nodes.forEach(node=>{node.open=true}));
 await visibleMasked();
 await page.screenshot({path:out+'/case-reviewed-masked.png',fullPage:false});
 const after=await(await context.request.get(api+'/findings?limit=100')).json();
 assert.deepEqual(after.findings.map(r=>[r.id,r.title,r.severity,r.status]),before.findings.map(r=>[r.id,r.title,r.severity,r.status]));
 assert.equal(blocked,0);assert.deepEqual(errors,[]);
 await fs.writeFile(out+'/review-fixes-receipt.json',JSON.stringify({status:'passed',read_only:true,
  utc_rule_window_visible:true,entity_context_filter:true,visual_masking_checked:true,
  original_finding_titles_severity_status_unchanged:true,blocked_requests:blocked,page_errors:errors},null,2));
 console.log('UTC wording, account context and visual presentation masking passed; recorded findings unchanged.');
}catch(error){await page.screenshot({path:out+'/review-fixes-failure.png',fullPage:true});throw error;}
finally{await context.close();await browser.close();}
