import assert from 'node:assert/strict';
import test from 'node:test';
import { shortFact, sourceTag } from '../../workspace_next/frontend/lib/factFormat.mjs';
const cases = [
  ['1 action kind(s) never seen in the last 28 days: ListObjects', 'new', '1 new action(s): ListObjects'],
  ['3 resource(s) never seen in the last 28 days: a, b, c', 'new', '3 new resource(s): a, b, c'],
  ['2 sensitive resource(s) not seen before: x', 'new', '2 new sensitive resource(s): x'],
  ["100% of today's events fall outside this account's usual hours (MYT)", 'pattern', '100% outside usual hours'],
  ['35 events today; median active day is 4 (8.8x)', 'pattern', '35 events · 8.8× a usual day (median 4)'],
  ['35 events today; median active day is 4.5 (7.8×)', 'pattern', '35 events · 7.8× a usual day (median 4.5)'],
  ['This account showed new actions on 3 of 5 recent active days, so novelty is discounted.', 'note', 'Novelty discounted: new actions on 3 of 5 recent days'],
];
test('shortFact rewrites known strings', () => { for (const [i, g, t] of cases) assert.deepEqual(shortFact(i), { group: g, text: t }); });
test('shortFact passes unknown strings through', () => assert.deepEqual(shortFact('something else'), { group: 'other', text: 'something else' }));
test('sourceTag', () => {
  assert.deepEqual(sourceTag('[aws_cloudtrail] hi'), { source: 'AWS', text: 'hi' });
  assert.deepEqual(sourceTag('[cloudflare_access] hi'), { source: 'Cloudflare', text: 'hi' });
  assert.deepEqual(sourceTag('[github_audit] hi'), { source: 'GitHub', text: 'hi' });
  assert.deepEqual(sourceTag('[other_x] hi'), { source: 'other_x', text: 'hi' });
  assert.deepEqual(sourceTag('hi'), { source: null, text: 'hi' });
});
import { scoreParts } from '../../workspace_next/frontend/lib/factFormat.mjs';
test('scoreParts sums to the score', () => {
  const r = scoreParts({ new_action: 1, new_resource: 1, unusual_hours: 1, volume: 0.4, sensitive_new: 0 }, 76);
  assert.equal(Math.round(r.parts.reduce((s, p) => s + p.points, 0)), 76); assert.equal(r.floor, 0);
});
test('scoreParts renormalises when new_resource is unavailable', () => {
  const r = scoreParts({ new_action: 0, new_resource: null, unusual_hours: 1, volume: 0.1, sensitive_new: 0 }, 29);
  assert.equal(r.parts.length, 4); assert.equal(Math.round(r.parts.reduce((s, p) => s + p.points, 0)), 29);
});
test('scoreParts reports the sensitive floor', () => assert.equal(scoreParts({ new_action: 0, new_resource: 0, unusual_hours: 0, volume: 0, sensitive_new: 0.5 }, 30).floor, 22));
test('scoreParts is null for Learning', () => assert.equal(scoreParts({}, null), null));
test('scoreParts whole points add up to the score', () => {
  const r = scoreParts({ new_action: 0.333, new_resource: 0.333, unusual_hours: 0.5, volume: 0.333, sensitive_new: 0 }, 32);
  assert.equal(r.parts.reduce((s, p) => s + p.pts, 0), 32);
});
import { attackTags } from '../../workspace_next/frontend/lib/factFormat.mjs';
test('attackTags maps the night data grab', () => {
  const tags = attackTags({ title: 'Baseline risk High (87): persona-02', details: { facts: ['1 action kind(s) never seen in the last 28 days: ListObjects', "100% of today's events fall outside this account's usual hours (MYT)"] } });
  assert.deepEqual(tags.map(t => t.id), ['T1078.004', 'T1619']);
});
test('attackTags maps a rule finding and stays empty without evidence', () => {
  assert.deepEqual(attackTags({ title: 'First-time action outside business hours for x' }).map(t => t.id), ['T1078.004']);
  assert.deepEqual(attackTags({ title: 'Baseline risk Medium (35)', details: { facts: ['35 events today; median active day is 4 (8.8x)'] } }), []);
});
