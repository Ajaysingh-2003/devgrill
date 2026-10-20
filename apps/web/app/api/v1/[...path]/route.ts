import { type NextRequest, NextResponse } from "next/server";
import { callerHeaders } from "@/lib/api";

/**
 * Same-origin door to the API for client components (the incident workspace): the browser
 * never holds the API token. The server adds the caller's credentials (the user's JWT, or the
 * guest token from its httpOnly cookie) and streams the answer back, Server-Sent Events
 * included.
 *
 * Cookies authenticate this route, so cross-site requests that change things are refused
 * (Origin must be this site): the CSRF guard.
 */
const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
const FORWARD_REQUEST = ["accept", "content-type", "idempotency-key", "last-event-id"];
const DROP_RESPONSE = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
]);

async function forward(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    const site = request.headers.get("sec-fetch-site");
    if ((origin && origin !== request.nextUrl.origin) || site === "cross-site") {
      return NextResponse.json(
        { type: "about:blank", title: "Forbidden", status: 403, code: "cross_site" },
        { status: 403, headers: { "content-type": "application/problem+json" } },
      );
    }
  }
  const { path } = await params;
  const target = `${API}/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers(await callerHeaders());
  for (const name of FORWARD_REQUEST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-request-id", crypto.randomUUID().replaceAll("-", ""));
  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return NextResponse.json(
      { type: "about:blank", title: "Service Unavailable", status: 503, code: "api_unreachable" },
      { status: 503, headers: { "content-type": "application/problem+json", "retry-after": "5" } },
    );
  }
  const out = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!DROP_RESPONSE.has(name.toLowerCase())) out.set(name, value);
  });
  if (out.get("content-type")?.startsWith("text/event-stream")) out.set("x-accel-buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as DELETE, forward as GET, forward as PATCH, forward as POST, forward as PUT };
