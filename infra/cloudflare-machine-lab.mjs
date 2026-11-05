// Machine-only toy target. Access policy grants one explicit service token.
export default {
  async fetch(request, env, ctx) {
    const headers = {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    };
    // Only the platform-supplied context is trusted, never request headers.
    if (!ctx?.access) return new Response("Access required", { status: 403, headers });
    if (request.method !== "GET") return new Response("Method not allowed", { status: 405, headers });
    if (!/^\/workloads\/persona-0[1-6]\/[a-z0-9-]{1,80}$/.test(new URL(request.url).pathname)) {
      return new Response("Not found", { status: 404, headers });
    }
    return new Response(
      "Argus machine workload: authenticated\nControlled machine activity; not a human login or anomaly-detection result.\n",
      { status: 200, headers },
    );
  },
};
