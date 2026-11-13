// Real saved readiness + case workflow on the explicitly marked isolated copy.
// Writes only a labelled verification case; no fake events or model outputs.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium }=await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui='http://127.0.0.1:3011',api='http://127.0.0.1:8015';
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[];let blocked=0;
page.on('pageerror',e=>errors.push(e.message));
await context.route('**/*',route=>{
  const req=route.request(),url=new URL(req.url());
  if(![ui,api].includes(url.origin)||(req.method()!=='GET'&&(url.origin!==api||!['POST','PATCH'].includes(req.method())||!url.pathname.startsWith('/cases')))){
    blocked++;return route.abort();
  }
  return route.continue();
});
try{
  assert.equal((await(await context.request.get(api+'/workspace/status')).json()).mode,'isolated_copy');
  const accounts=await(await context.request.get(api+'/workspace/accounts')).json();
  const findings=await(await context.request.get(api+'/findings?limit=100')).json();
  const selected=findings.findings.find(f=>accounts.some(a=>a.account_key===f.user_id&&a.account_label.includes('persona-02')))
    ||findings.findings.find(f=>accounts.some(a=>a.account_key===f.user_id&&a.account_label.includes('persona-')));
  assert.ok(selected,'A genuine controlled-workload finding in the copied store is required.');
  await page.goto(ui+'/workspace?finding='+selected.id,{waitUntil:'networkidle'});
  const finding=page.getByRole('dialog',{name:'Finding #'+selected.id});
  await finding.getByText('Account-day diagnostic context',{exact:true}).click();
  await finding.getByLabel('Activity day (MYT)').fill('2026-10-30');
  await finding.getByText('Coverage and provenance',{exact:true}).waitFor();
  assert.equal(await finding.getByText(/raw reconstruction error/).count(),0);
  await finding.getByRole('button',{name:'Create case',exact:true}).click();
  await finding.getByLabel('Title',{exact:true}).fill('POC diagnostic workflow verification — isolated copy');
  await finding.getByLabel('Owner',{exact:true}).fill('POC reviewer');
  await finding.getByLabel('Analyst',{exact:true}).fill('POC test');
  await finding.getByLabel('Reason',{exact:true}).fill('Inspect real saved activity and input readiness; no compromise claim.');
  await finding.getByRole('checkbox').check();
  await finding.getByRole('button',{name:'Create case with finding',exact:true}).click();
  await page.waitForURL('**/cases/*');
  const caseId=new URL(page.url()).pathname.split('/').pop();
  await page.getByRole('button',{name:/Inspect event #/}).first().click();
  const event=page.getByRole('dialog');
  const panel=event.getByRole('region',{name:'Account-day model diagnostic'});
  await panel.getByLabel('Activity day (MYT)').fill('2026-10-30');
  await panel.getByText('Coverage and provenance',{exact:true}).waitFor();
  await panel.getByLabel('Analyst for diagnostic context').fill('POC test');
  await panel.getByLabel('Reason for retaining context').fill('Preserve the reviewed history and coverage gap with this case.');
  const retainedResponse=page.waitForResponse(r=>r.url()===api+'/cases/'+caseId+'/diagnostics'&&r.request().method()==='POST');
  await panel.getByRole('button',{name:'Retain diagnostic context',exact:true}).click();
  const response=await retainedResponse;
  assert.equal(response.status(),200,await response.text());
  const retained=await response.json();
  const diagnostic=retained.links.find(link=>link.kind==='diagnostic');
  assert.ok(diagnostic);
  assert.equal(diagnostic.snapshot.association,'account_day_context_not_trigger_attribution');
  assert.deepEqual(diagnostic.snapshot.receipt.detectors,{});
  assert.equal(diagnostic.snapshot.risk_tier,null);
  await event.getByRole('button',{name:'Close',exact:true}).click();
  await page.getByRole('heading',{name:'Retained diagnostic context',exact:true}).waitFor();
  const retainedSection=page.getByRole('heading',{name:'Retained diagnostic context',exact:true}).locator('..');
  await retainedSection.locator('summary').first().click();
  assert.ok(!(await retainedSection.innerText()).includes(diagnostic.snapshot.receipt.key.scope),'Provider scope must be masked in displayed diagnostic context.');
  await page.getByLabel('Analyst',{exact:true}).fill('POC test');
  await page.getByLabel('Notes',{exact:true}).fill('Input readiness reviewed and retained; no AE score was available.');
  await page.getByLabel('Close this case',{exact:true}).check();
  await page.getByLabel('Resolution',{exact:true}).selectOption('Insufficient evidence');
  await page.getByLabel('Closing reason',{exact:true}).fill('Controlled-workload history is insufficient for inference; no compromise conclusion.');
  const closedResponse=page.waitForResponse(r=>r.url()===api+'/cases/'+caseId&&r.request().method()==='PATCH');
  await page.getByRole('button',{name:'Save decision and close',exact:true}).click();
  assert.equal((await closedResponse).status(),200);
  const closed=await(await context.request.get(api+'/cases/'+caseId)).json();
  assert.equal(closed.status,'Closed');
  assert.deepEqual(closed.links,retained.links);
  assert.equal((await(await context.request.get(api+'/findings/'+selected.id)).json()).status,selected.status);
  assert.equal(blocked,0);assert.deepEqual(errors,[]);
  await fs.writeFile('data/live/poc-workflow-ui-20261101.json',JSON.stringify({
    passed:true,isolated_copy:true,case_id:caseId,real_saved_readiness:true,
    finding_to_context_to_case_to_decision:true,model_scores_displayed:false,
    diagnostic_snapshot_preserved:true,finding_status_unchanged:true,errors,blocked_requests:blocked
  },null,2));
  console.log('POC workflow passed with real saved readiness and a labelled isolated verification case.');
}finally{await browser.close();}
