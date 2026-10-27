// Optional local browser smoke check. Uses a fresh headless Chrome profile;
// never attaches to the user's browser, writes live data, or calls cloud APIs.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const modulePath = process.env.ARGUS_PLAYWRIGHT_MODULE;
if (!modulePath) throw new Error('Set ARGUS_PLAYWRIGHT_MODULE to an installed Playwright entry point');
const { chromium } = await import(pathToFileURL(modulePath).href);
const ui = process.env.ARGUS_UI_URL || 'http://127.0.0.1:3010';
const api = process.env.ARGUS_API_URL || 'http://127.0.0.1:8010';
for (const url of [ui, api]) if (new URL(url).hostname !== '127.0.0.1') throw new Error('Loopback only');
const output = process.env.ARGUS_UI_OUTPUT || 'data/live/replay-ui';
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1500, height: 1150 }, deviceScaleFactor: 1.5 });
const page = await context.newPage();
const failures = [];
page.on('pageerror', error => failures.push(error.message));
await page.route('**/*', route => {
  const request = route.request();
  const origin = new URL(request.url()).origin;
  return request.method() === 'GET' && [new URL(ui).origin, new URL(api).origin].includes(origin)
    ? route.continue() : route.abort();
});
async function json(path) {
  const response = await context.request.get(api + path);
  assert.equal(response.status(), 200);
  return response.json();
}
async function summaryHas(value) {
  await page.getByRole('region', { name: 'Review priority summary' }).getByText(String(value), { exact: true }).waitFor();
}
try {
  const before = await json('/stats');
  assert.equal(before.application_mode, 'live');
  assert.equal(before.total_users, before.unscored_users);
  const meta = await json('/replay/clue/metadata');
  assert.deepEqual(meta.splits.heldout.counts, { Low: 185, Medium: 4, High: 2 });
  await page.goto(ui + '/clue', { waitUntil: 'networkidle' });
  await summaryHas(191);
  await page.getByText('0.128221', { exact: false }).waitFor();
  assert.equal(await page.getByRole('link', { name: 'Demo Lab', exact: true }).count(), 0);
  await page.screenshot({ path: output + '/clue-heldout.png', fullPage: true });
  await page.getByRole('button', { name: /^Inspect cohort-/ }).first().click();
  await page.getByRole('region', { name: 'Numerical reconstruction evidence' }).waitFor();
  await page.getByRole('region', { name: 'Numerical reconstruction evidence' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: output + '/clue-evidence.png', fullPage: true });
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByLabel('Review priority', { exact: true }).selectOption('Medium');
  await page.getByText('4 matching account-days', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Calibration diagnostics', exact: true }).click();
  await summaryHas(169);
  await page.getByText('They are calibration diagnostics, not independent test results.', { exact: false }).waitFor();
  await page.screenshot({ path: output + '/clue-calibration.png', fullPage: true });
  await page.goto(ui + '/', { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Account Risk Overview' }).waitFor();
  await page.getByRole('cell', { name: 'Unknown', exact: true }).first().waitFor();
  await page.screenshot({ path: output + '/connected-sources.png', fullPage: true });
  const after = await json('/stats');
  assert.deepEqual(after, before);
  assert.equal(failures.length, 0, failures.join('\n'));
  await fs.writeFile(output + '/browser-check.json', JSON.stringify({ status: 'passed',
    heldout_account_days: 191, priorities: meta.splits.heldout.counts,
    connected_accounts: before.total_users, connected_unscored: before.unscored_users,
    calibration_label_checked: true, medium_filter_checked: true,
    residual_details_checked: true, live_stats_unchanged: true, page_errors: failures }, null, 2));
  console.log('Replay browser checks passed; screenshots and report saved locally.');
} finally {
  await context.close();
  await browser.close();
}
