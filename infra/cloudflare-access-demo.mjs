// Minimal authentication target. This is not an Argus API or ingest endpoint.
export default {
  async fetch(request, env, ctx) {
    const headers = {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    };
    // Trust only the runtime's Access context, never client-supplied headers.
    if (!ctx?.access || !env.ALLOWED_EMAIL) {
      return new Response("Access required", { status: 403, headers });
    }
    let identity;
    try {
      identity = await ctx.access.getIdentity();
    } catch {
      return new Response("Access required", { status: 403, headers });
    }
    if (typeof identity?.email !== "string" ||
        identity.email.toLowerCase() !== env.ALLOWED_EMAIL.toLowerCase()) {
      return new Response("Access denied", { status: 403, headers });
    }
    return new Response(
      "Argus Access test: authentication succeeded.\n" +
      "This page generates a real Cloudflare Access login event.\n" +
      "It does not demonstrate anomaly detection or in-app activity monitoring.\n",
      { status: 200, headers },
    );
  },
};
