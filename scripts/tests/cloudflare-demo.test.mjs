import test from "node:test";
import assert from "node:assert/strict";
import worker from "../../infra/cloudflare-access-demo.mjs";

const request = new Request("https://example.invalid/", {
  headers: { "Cf-Access-Authenticated-User-Email": "reviewer@example.com" },
});
const env = { ALLOWED_EMAIL: "reviewer@example.com" };
const context = (email) => ({ access: { getIdentity: async () => ({ email }) } });

test("client-supplied Access headers cannot authenticate a caller", async () => {
  assert.equal((await worker.fetch(request, env, {})).status, 403);
});
test("missing allow configuration and wrong identities are denied", async () => {
  assert.equal((await worker.fetch(request, {}, context(env.ALLOWED_EMAIL))).status, 403);
  assert.equal((await worker.fetch(request, env, context("other@example.com"))).status, 403);
  assert.equal((await worker.fetch(request, env, context(undefined))).status, 403);
});
test("identity service failures are denied", async () => {
  const ctx = { access: { getIdentity: async () => { throw new Error("private details"); } } };
  const response = await worker.fetch(request, env, ctx);
  assert.equal(response.status, 403);
  assert.doesNotMatch(await response.text(), /private details/);
});
test("authenticated approved identity receives a static uncached page", async () => {
  const response = await worker.fetch(request, env, context("Reviewer@Example.com"));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  const body = await response.text();
  assert.match(body, /authentication succeeded/);
  assert.doesNotMatch(body, /reviewer@example.com/i);
});
