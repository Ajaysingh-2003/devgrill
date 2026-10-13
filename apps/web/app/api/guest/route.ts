import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createGuestToken } from "@devgrill/api-client";
import { api } from "@/lib/api";
import { GUEST_COOKIE } from "@/lib/guest";

/**
 * Start a guest session for /try: the API signs a guest token, kept in an httpOnly cookie
 * (scripts can't read it). Attempts played as a guest are claimed after sign-up.
 */
export async function POST() {
  const jar = await cookies();
  if (jar.get(GUEST_COOKIE)) return NextResponse.json({ ok: true, existing: true });
  const { data, response } = await createGuestToken({ client: await api() });
  if (!data) {
    return NextResponse.json({ ok: false }, { status: response?.status === 429 ? 429 : 502 });
  }
  jar.set(GUEST_COOKIE, data.token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production" && !process.env.BETTER_AUTH_URL?.startsWith("http:"),
    path: "/",
    expires: new Date(data.expires_at),
  });
  return NextResponse.json({ ok: true, existing: false });
}
