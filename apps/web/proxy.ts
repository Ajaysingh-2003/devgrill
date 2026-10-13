import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic auth gate for pages that only make sense signed in: no session cookie, go to
 * sign-in and come back. This only checks the cookie exists; the page (and the API) still
 * validate the session for real.
 */
export function proxy(request: NextRequest) {
  if (getSessionCookie(request, { cookiePrefix: "devgrill" })) return NextResponse.next();
  const url = new URL("/sign-in", request.url);
  url.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/settings/:path*", "/admin/:path*"],
};
