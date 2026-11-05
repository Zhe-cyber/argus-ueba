// Mutates only the explicitly marked isolated workspace copy on port 8015.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui='http://127.0.0.1:3011',api='http://127.0.0.1:8015';
const output='data/live/workspace-case-preview-20261030-v1/browser';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[]; let mutations=0,unexpected=0;
context.on('page',p=>p.on('pageerror',error=>errors.push(error.message)));
page.on('pageerror',error=>errors.push(error.message));
await context.route('**/*',route=>{
 const req=route.request(),origin=new URL(req.url()).origin;
 if(![ui,api].includes(origin)){unexpected++;return route.abort();}
 if(req.method()!=='GET'){
  if(origin!==api||!['POST','PATCH'].includes(req.method())||!new URL(req.url()).pathname.startsWith('/cases')){unexpected++;return route.abort();}
  mutations++;
 }
 return route.continue();
});
try{
 assert.equal((await(await context.request.get(api+'/workspace/status')).json()).mode,'isolated_copy');
 const accounts=await(await context.request.get(api+'/workspace/accounts')).json();
 const findings=await(await context.request.get(api+'/findings?limit=100')).json();
 const people=await(await context.request.get(api+'/workspace/people')).json();
 const person=people.find(row=>row.active_links>1);
 const personAccounts=person?.links.filter(link=>link.effective_status==='approved').map(link=>link.account_key)||[];
 const selected=findings.findings.find(row=>personAccounts.includes(row.user_id))||findings.findings.find(row=>accounts.some(account=>account.account_key===row.user_id));
 assert.ok(selected);
 const initial=(await(await context.request.get(api+'/cases')).json()).cases.length;
 await page.goto(ui+'/workspace',{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:'Work queue',exact:true}).waitFor();
 await page.getByRole('button',{name:'Review #'+selected.id,exact:true}).click();
 await page.getByRole('dialog',{name:'Finding #'+selected.id}).waitFor();
 await page.getByRole('button',{name:'Create case',exact:true}).click();
 await page.getByLabel('Title',{exact:true}).fill('Workflow verification — isolated copy');
 await page.getByLabel('Owner',{exact:true}).fill('Reviewer');
 await page.getByLabel('Analyst',{exact:true}).fill('Workflow check');
 await page.getByLabel('Reason',{exact:true}).fill('Review the retained source evidence');
 await page.getByRole('checkbox').check();
 await page.getByRole('button',{name:'Create case with finding',exact:true}).click();
 await page.waitForURL('**/cases/*');
 const id=new URL(page.url()).pathname.split('/').pop();
 await page.getByRole('heading',{name:'Evidence timeline',exact:true}).waitFor();
 await page.getByRole('button',{name:/Inspect event #/}).first().waitFor();
 await page.getByRole('button',{name:/Inspect event #/}).first().click();
 await page.getByRole('dialog').waitFor();
 assert.ok((await page.getByRole('dialog').innerText()).includes('normalized_event'));
 await page.getByRole('button',{name:'Close',exact:true}).click();
 await page.getByLabel('Analyst',{exact:true}).fill('Workflow check');
 if(person){
  await page.getByLabel('Add context',{exact:false}).selectOption('person');
  await page.getByLabel('Entity',{exact:false}).selectOption(person.id);
  await page.getByLabel('Reason',{exact:true}).fill('Review activity through the existing approved identity mappings.');
  const linked=page.waitForResponse(response=>response.url()===api+'/cases/'+id+'/links'&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Add to case',exact:true}).click();
  assert.equal((await linked).status(),200);
  const timeline=await(await context.request.get(api+'/cases/'+id+'/timeline?limit=100')).json();
  assert.ok(timeline.mapping_provenance.length>1);
  assert.ok(new Set(timeline.events.map(row=>row.source)).size>1);
 }
 const stale=await context.newPage();
 await stale.goto(ui+'/cases/'+id,{waitUntil:'networkidle'});
 await stale.getByLabel('Analyst',{exact:true}).fill('Other reviewer');
 await page.getByLabel('Notes',{exact:true}).fill('Evidence reviewed against the source timeline.');
 const saved=page.waitForResponse(response=>response.url()===api+'/cases/'+id&&response.request().method()==='PATCH');
 await page.getByRole('button',{name:'Save notes',exact:true}).click();
 assert.equal((await saved).status(),200);
 await stale.getByLabel('Notes',{exact:true}).fill('Stale replacement must not win');
 await stale.getByRole('button',{name:'Save notes',exact:true}).click();
 await stale.getByRole('alert').waitFor();
 const current=await(await context.request.get(api+'/cases/'+id)).json();
 assert.equal(current.notes,'Evidence reviewed against the source timeline.');
 await stale.close();
 await page.getByLabel('Close this case',{exact:true}).check();
 await page.getByLabel('Resolution',{exact:true}).selectOption('Expected or authorized activity');
 await page.getByLabel('Closing reason',{exact:true}).fill('Approved controlled activity in the isolated copy.');
 await page.getByRole('button',{name:'Save decision and close',exact:true}).click();
 await page.getByText('Closed',{exact:true}).first().waitFor();
 const closed=await(await context.request.get(api+'/cases/'+id)).json();
 assert.equal(closed.status,'Closed');
 assert.equal((await(await context.request.get(api+'/findings/'+selected.id)).json()).status,selected.status);
 assert.equal((await(await context.request.get(api+'/cases')).json()).cases.length,initial+1);
 await page.screenshot({path:output+'/case-closed.png',fullPage:true});
 await page.goto(ui+'/workspace',{waitUntil:'networkidle'});
 await page.getByLabel('Finding category').selectOption('observation');
 await page.waitForURL('**category=observation*');
 await page.getByRole('button',{name:/Review #/}).first().waitFor();
 await page.screenshot({path:output+'/queue-observations.png',fullPage:false});
 assert.equal(unexpected,0); assert.deepEqual(errors,[]);
 await fs.writeFile(output+'/receipt.json',JSON.stringify({status:'passed',isolated_copy:true,case_id:id,
  finding_to_evidence_to_case_to_decision:true,approved_cross_provider_timeline:!!person,stale_edit_rejected:true,finding_disposition_unchanged:true,
  unexpected_requests:unexpected,copy_mutation_requests:mutations,page_errors:errors},null,2));
 console.log('Case workflow passed on isolated copy; stale edit rejected; finding disposition unchanged.');
}catch(error){await page.screenshot({path:output+'/failure.png',fullPage:true});throw error;}
finally{await context.close();await browser.close();}
