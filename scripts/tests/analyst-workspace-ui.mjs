// Fresh headless browser; loopback GETs only. No writes to the pilot database.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(process.env.ARGUS_PLAYWRIGHT_MODULE).href);
const ui = process.env.ARGUS_UI_URL || 'http://127.0.0.1:3000', api = 'http://127.0.0.1:8013';
const output = process.env.ARGUS_UI_OUTPUT || 'data/live/dashboard-w24';
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const failures = [];
let blockedMutations = 0;
page.on('pageerror', error => failures.push(error.message));
await page.route('**/*', async route => {
  const request = route.request();
  if (request.method() !== 'GET') blockedMutations++;
  if (request.method() !== 'GET' || ![ui, api].includes(new URL(request.url()).origin)) return route.abort();
  // Isolated build ports are outside the API's production CORS allowlist.
  // Serve read-only API responses through the test interceptor; no API config change.
  if (ui !== 'http://127.0.0.1:3000' && new URL(request.url()).origin === api) {
    const response = await route.fetch();
    return route.fulfill({ response, headers: { ...response.headers(), 'access-control-allow-origin': ui } });
  }
  return route.continue();
});
try {
  const before = await (await context.request.get(api + '/stats')).json();
  await page.goto(ui, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Overview' }).waitFor();
  await page.getByText('Observed', { exact: true }).first().waitFor();
  assert.equal(await page.getByRole('link', { name: 'Demo Lab' }).count(), 0);
  assert.equal(await page.getByText('High priority', { exact: true }).count(), 0);
  await page.screenshot({ path: output + '/connected-activity.png', fullPage: true });
  await page.screenshot({ path: output + '/source-overview.png', clip: { x: 60, y: 60, width: 1320, height: 610 } });
  const accountRows = await (await context.request.get(api + '/users?limit=100')).json();
  const account = accountRows.users.find(row => row.user.startsWith('acct_'));
  assert.ok(account && account.display_name);
  await page.goto(ui + '/users/' + encodeURIComponent(account.user), { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: account.display_name, exact: true }).waitFor();
  assert.equal(await page.getByText('Live AE', { exact: true }).count(), 0);
  assert.equal(await page.getByText('SHAP values not available for this user.', { exact: true }).count(), 0);
  assert.equal(await page.getByRole('region', { name: 'Score breakdown', exact: true }).count(), 0);
  await page.getByRole('status', { name: 'Scoring readiness' }).waitFor();
  await page.getByText('Identity', { exact: true }).click();
  await page.getByText('Basis: ' + account.identity_basis, { exact: true }).waitFor();
  await page.goto(ui + '/', { waitUntil: 'networkidle' });
  await page.getByRole('link', { name: 'View alerts →' }).click();
  await page.getByRole('heading', { name: 'Alert review', exact: true }).waitFor();
  await page.getByTestId('alert-row').first().waitFor();
  assert.equal(await page.getByLabel('Signal origin', { exact: true }).inputValue(), 'Security findings');
  assert.equal(await page.getByTestId('alert-row').filter({ hasText: '· Observation' }).count(), 0);
  await page.getByLabel('Signal origin', { exact: true }).selectOption('Observation');
  assert.ok(await page.getByTestId('alert-row').count() > 0);
  await page.getByLabel('Signal origin', { exact: true }).selectOption('Security findings');
  await page.getByRole('button', { name: 'Investigate →', exact: true }).first().click();
  await page.getByRole('region', { name: 'Confirm investigation', exact: true }).waitFor();
  await page.screenshot({ path: output + '/alert-review.png', fullPage: false });
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  assert.equal(await page.getByRole('region', { name: 'Confirm investigation' }).count(), 0);
  await page.goto(ui + '/investigations', { waitUntil: 'networkidle' });
  assert.equal(await page.getByText('Quick-start: import High-risk', { exact: true }).count(), 0);
  await page.goto(ui + '/demo', { waitUntil: 'networkidle' });
  assert.equal(new URL(page.url()).pathname, '/');
  const after = await (await context.request.get(api + '/stats')).json();
  // Other collector processes can legitimately add events during this check.
  // Prove our browser sent no mutations instead of requiring a frozen live DB.
  assert.equal(blockedMutations, 0);
  assert.deepEqual(failures, []);
  await fs.writeFile(output + '/browser-check.json', JSON.stringify({ status: 'passed',
    mutations_sent: 0, source_cards: true, origin_filters: true, compact_scoring: true, security_default: true,
    escalation_review_and_cancel: true, scoped_account_profile: true, demo_redirect: true,
    live_stats_unchanged: JSON.stringify(after) === JSON.stringify(before), blocked_mutations: blockedMutations,
    page_errors: failures }, null, 2));
  console.log('Analyst workspace browser checks passed. No pilot writes.');
} finally { await context.close(); await browser.close(); }
