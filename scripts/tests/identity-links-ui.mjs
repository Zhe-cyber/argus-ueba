// Optional owned-local-pilot smoke test. Fresh browser, no actual writes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui = 'http://127.0.0.1:3000', api = 'http://127.0.0.1:8013';
const output = 'data/live/identity-links-release-v1';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
const page = await context.newPage();
const failures = [];
page.on('pageerror', error => failures.push(error.message));
await page.route('**/*', route => {
  const request = route.request();
  return request.method() === 'GET' && [ui, api].includes(new URL(request.url()).origin)
    ? route.continue() : route.abort();
});
const json = async path => (await context.request.get(api + path)).json();
try {
  const before = await json('/identities');
  const stats = await json('/stats');
  const owner = before.find(person => person.active_links === 2);
  assert.ok(owner);
  const timeline = await json('/identities/' + owner.id + '/timeline');
  assert.deepEqual(timeline.linked_sources, ['cloudflare_access', 'github_events']);
  assert.ok(timeline.events.length > 0 && timeline.events.every(event => event.source !== 'aws_cloudtrail'));
  await page.goto(ui, { waitUntil: 'networkidle' });
  await page.getByRole('link', { name: 'Identities', exact: true }).click();
  await page.getByRole('heading', { name: owner.display_name, exact: true }).waitFor();
  await page.getByText('2 approved account links', { exact: true }).waitFor();
  await page.getByText('AWS not linked', { exact: true }).waitFor();
  const panel = page.getByRole('region', { name: 'Linked accounts' });
  for (const link of owner.links) {
    await panel.getByRole('link', { name: link.account.account_label, exact: true }).waitFor();
  }
  await page.getByLabel('Timeline source', { exact: true }).selectOption('cloudflare_access');
  const rows = page.getByRole('region', { name: 'Cross-provider timeline' }).locator('tbody tr');
  assert.ok(await rows.count() > 0);
  for (const row of await rows.all()) assert.ok((await row.innerText()).includes('Cloudflare'));
  await page.getByLabel('Timeline source', { exact: true }).selectOption('all');
  await panel.getByText('Approval details', { exact: true }).first().click();
  await page.getByText('Recorded by: Account owner (chat confirmation)', { exact: true }).first().waitFor();
  await page.screenshot({ path: output + '/identities.png', fullPage: false });
  await panel.getByRole('button', { name: 'Revoke', exact: true }).first().click();
  await page.getByRole('heading', { name: 'Revoke account link', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  assert.deepEqual(await json('/identities'), before);
  assert.deepEqual(await json('/stats'), stats);
  assert.deepEqual(failures, []);
  await fs.writeFile(output + '/browser-check.json', JSON.stringify({ status: 'passed',
    approved_sources: timeline.linked_sources, timeline_events: timeline.events.length,
    source_filter: true, approval_provenance: true, revocation_cancel: true,
    identity_state_unchanged: true, live_stats_unchanged: true, pilot_writes: 0,
    page_errors: failures }, null, 2));
  console.log('Identity UI passed: approved mapping, timeline/filter, provenance and no pilot writes.');
} finally { await context.close(); await browser.close(); }
