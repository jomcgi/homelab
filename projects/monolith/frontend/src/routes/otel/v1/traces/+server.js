import { env } from "$env/dynamic/private";

/** @type {import('./$types').RequestHandler} */
export async function POST({ request }) {
  const collectorUrl = env.OTEL_COLLECTOR_HTTP_URL;
  if (!collectorUrl) {
    return new Response(null, { status: 204 });
  }

  const resp = await fetch(`${collectorUrl}/v1/traces`, {
    method: "POST",
    headers: {
      "Content-Type": request.headers.get("Content-Type") || "application/json",
    },
    body: await request.arrayBuffer(),
    signal: AbortSignal.timeout(5000),
  });

  return new Response(resp.body, { status: resp.status });
}
