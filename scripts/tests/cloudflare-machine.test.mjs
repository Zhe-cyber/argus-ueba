import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../../infra/cloudflare-machine-lab.mjs';
const request=new Request('https://example.test/workloads/persona-01/commissioning',{
  headers:{'CF-Access-Client-Id':'forged','CF-Access-Authenticated-User-Email':'forged@example.test'},
});
test('client headers cannot create trusted Access context',async()=>{
  assert.equal((await worker.fetch(request,{},{})).status,403);
});
test('authenticated toy request returns static uncached response',async()=>{
  const response=await worker.fetch(request,{},{access:{}});
  assert.equal(response.status,200);
  assert.equal(response.headers.get('Cache-Control'),'no-store');
  assert.doesNotMatch(await response.text(),/forged/);
});
test('target accepts no writes and only bounded toy paths',async()=>{
  assert.equal((await worker.fetch(new Request(request.url,{method:'POST'}),{},{access:{}})).status,405);
  assert.equal((await worker.fetch(new Request('https://example.test/admin'),{},{access:{}})).status,404);
});
