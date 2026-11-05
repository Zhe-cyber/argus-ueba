// Read-only isolated preview test. Scored output below is a browser-only synthetic fixture.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui='http://127.0.0.1:3011', api='http://127.0.0.1:8015';
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[]; let blocked=0;
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/*',route=>{
  const request=route.request();
  if(request.method()!=='GET'||![ui,api].includes(new URL(request.url()).origin)){blocked++;return route.abort();}
  return route.continue();
});
try {
  await page.goto(ui+'/entities',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Inspect',exact:true}).first().click();
  const panel=page.getByRole('region',{name:'Account-day model diagnostic'});
  await panel.getByLabel('Activity day (MYT)').fill('2026-10-30');
  await panel.getByText('Model diagnostics are not enabled.',{exact:true}).waitFor();
  assert.equal(await panel.getByText(/raw reconstruction error/).count(),0);
  await page.route(api+'/workspace/diagnostics?*',route=>route.fulfill({json:{
    status:'diagnostic',mode:'recorded',cutoff_utc:'2026-11-01T00:00:00Z',live_activation:false,risk_tier:null,
    history_scopes:{expanding_history_days:Array(30).fill('fixture'),rolling_window_days:Array(28).fill('fixture')},
    receipt:{schema:'clue_v2_live_diagnostic_receipt_v2',receipt_id:'0'.repeat(64),input:{},
      coverage:{policy_status:'outside_policy_completeness_unknown'},completeness:'unknown',facts:[],
      detectors:{B:{score_raw_mse:1,terms:[{feature:'event_count',text:'Synthetic event-count term',share_of_reconstruction_error:1}]}}}
  }}));
  await panel.getByLabel('Activity day (MYT)').fill('2026-10-29');
  await panel.getByText('Experimental model output',{exact:true}).waitFor();
  await panel.getByText('B · raw reconstruction error 1.000',{exact:true}).click();
  await panel.getByText('Synthetic event-count term · 100.0% of reconstruction error',{exact:true}).waitFor();
  await panel.getByText('History: 30 accepted days for action novelty · 28 for recent behaviour.',{exact:true}).waitFor();
  assert.equal(await panel.getByText(/High risk|Low risk|SHAP/).count(),0);
  assert.deepEqual(errors,[]); assert.equal(blocked,0);
  await fs.writeFile('data/live/diagnostic-panel-ui-20261101.json',JSON.stringify({
    passed:true,console_errors:errors,non_get_or_external_requests_blocked:blocked,
    scored_view:'browser_only_synthetic_fixture',real_diagnostics_enabled:false,live_store_modified:false
  },null,2));
  console.log('Diagnostic panel: real disabled-state and synthetic score/history views passed.');
} finally {await browser.close();}
