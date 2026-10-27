import { NextResponse, type NextRequest } from "next/server";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * One-click unsubscribe (RFC 8058): mail clients POST here from the List-Unsubscribe header.
 * The signed token in the URL is the only credential (no cookies), so a cross-site POST is fine.
 */
export async function POST(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token") ?? "";
  const res = await fetch(`${API}/v1/emails/pause?token=${encodeURIComponent(token)}`, {
    method: "POST",
    cache: "no-store",
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
