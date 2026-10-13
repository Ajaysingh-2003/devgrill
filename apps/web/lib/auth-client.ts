"use client";

import { createAuthClient } from "better-auth/react";
import { jwtClient } from "better-auth/client/plugins";

/** Browser side of Better Auth (same origin, so no base URL needed). */
export const authClient = createAuthClient({ plugins: [jwtClient()] });

/** GitHub sign-in; lands on /auth/complete (claims guest attempts) and then on `next`. */
export function signInWithGitHub(next: string) {
  return authClient.signIn.social({
    provider: "github",
    callbackURL: `/auth/complete?next=${encodeURIComponent(next)}`,
    errorCallbackURL: "/sign-in?error=1",
  });
}
