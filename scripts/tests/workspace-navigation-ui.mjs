// Read-only navigation check on the isolated preview; no live origins allowed.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const {chromium}=await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui='http://127.0.0.1:3011',api='http://127.0.0.1:8015';
const out='data/live/workspace-case-preview-20261030-v1/browser';
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[],requests=[]; let blocked=0;
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/*',route=>{
 const request=route.request();
 if(request.method()!=='GET'||![ui,api].includes(new URL(request.url()).origin)){blocked++;return route.abort();}
 requests.push(request.url());return route.continue();
});
try{
 await page.goto(ui,{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:'Overview',exact:true}).waitFor();
 const nav=page.getByRole('navigation',{name:'Workspace navigation'});
 assert.equal(await nav.getByRole('link').count(),5);
 await page.getByText('Open security findings',{exact:true}).waitFor();
 await page.screenshot({path:out+'/overview.png',fullPage:true});
 await nav.getByRole('link',{name:'Connections',exact:true}).click();
 await page.getByRole('heading',{name:'Connections',exact:true}).waitFor();
 await page.getByRole('heading',{name:'AWS CloudTrail',exact:true}).waitFor();
 await page.getByText(/Operational snapshot:/).waitFor();
 const status=await(await context.request.get(api+'/workspace/connections')).json();
 const idle=status.sources.filter(source=>source.activity_window?.status==='outside_hours').length;
 if(idle) assert.equal(await page.getByText('Outside activity hours · 08:00–20:00 MYT',{exact:true}).count(),idle);
 for(const source of status.sources){
  if(source.workload.attention_scope==='historical'){
   assert.equal(source.workload_history.today.unresolved,0);
   assert.ok(source.workload_history.prior_days.unresolved>0);
   await page.getByText('Previous outcome unresolved',{exact:true}).waitFor();
  }
 }

 assert.equal(await page.getByText('Microsoft Entra ID',{exact:true}).count(),0);
 await page.screenshot({path:out+'/connections.png',fullPage:true});
 await nav.getByRole('link',{name:'Entities',exact:true}).click();
 await page.getByRole('heading',{name:'Entities',exact:true}).waitFor();
 await page.getByRole('button',{name:'People',exact:true}).click();
 await page.getByRole('button',{name:'Inspect',exact:true}).first().click();
 await page.getByRole('link',{name:'Account findings →',exact:true}).first().click();
 await page.getByRole('heading',{name:'Work queue',exact:true}).waitFor();
 assert.ok(new URL(page.url()).searchParams.get('account'));
 await page.getByText(/Account filter:/).waitFor();
 const id=(await(await context.request.get(api+'/cases')).json()).cases[0].id;
 const start='2017-01-01T00:00',end='2027-01-01T00:00';
 await page.goto(ui+'/cases/'+id+'?'+new URLSearchParams({provider:'github_events',start,end}),{waitUntil:'networkidle'});
 await page.getByRole('link',{name:'Check collection context →',exact:true}).click();
 await page.getByRole('heading',{name:'Connections',exact:true}).waitFor();
 await page.getByRole('heading',{name:'GitHub',exact:true}).waitFor();
 assert.equal(await page.getByRole('heading',{name:'AWS CloudTrail',exact:true}).count(),0);
 await page.getByRole('link',{name:'← Return to case with timeline filters',exact:true}).click();
 await page.getByRole('heading',{name:'Evidence timeline',exact:true}).waitFor();
 assert.equal(new URL(page.url()).searchParams.get('provider'),'github_events');
 assert.equal(new URL(page.url()).searchParams.get('start'),start);
 assert.equal(new URL(page.url()).searchParams.get('end'),end);
 await page.setViewportSize({width:390,height:844});
 await page.goto(ui+'/connections',{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:'Connections',exact:true}).waitFor();
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
 await page.screenshot({path:out+'/connections-mobile.png',fullPage:true});
 assert.equal(blocked,0);assert.deepEqual(errors,[]);
 await fs.writeFile(out+'/navigation-receipt.json',JSON.stringify({status:'passed',read_only:true,
  navigation_views:5,dated_operational_receipts:true,idle_window_distinct:true,historical_outcomes_separate:true,entity_to_filtered_queue:true,
  case_time_context_preserved:true,mobile_no_horizontal_overflow:true,
  blocked_requests:blocked,page_errors:errors},null,2));
 console.log('Navigation, Connections, entity pivots and case filter preservation passed; no writes.');
}catch(error){await page.screenshot({path:out+'/navigation-failure.png',fullPage:true});throw error;}
finally{await context.close();await browser.close();}
