import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { claimGuest } from "@devgrill/api-client";
import { api } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { safeNext } from "@/lib/safe-next";
import { GUEST_COOKIE } from "@/lib/guest";

/**
 * Where GitHub sign-in lands. If this browser played as a guest, attach those attempts to the
 * account (POST /v1/me/claim-guest), forget the guest cookie, then continue to `next`.
 */
export async function GET(request: NextRequest) {
  const next = safeNext(request.nextUrl.searchParams.get("next") ?? undefined);
  const destination = new URL(next, request.url);
  const jar = await cookies();
  const guestToken = jar.get(GUEST_COOKIE)?.value;

  if (guestToken && (await getSession())) {
    const { response } = await claimGuest({ client: await api(), body: { guest_token: guestToken } });
    // An invalid or expired guest token can't be claimed later either: drop it in any case.
    if (response?.ok || response?.status === 400) jar.delete(GUEST_COOKIE);
  }
  return NextResponse.redirect(destination);
}
