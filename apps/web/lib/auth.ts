import "server-only";
import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { nextCookies } from "better-auth/next-js";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import { authConfig } from "./auth-config.mts";
import { syncProfile } from "./internal-api";

const config = authConfig();

export const auth = betterAuth({
  ...config,
  hooks: {
    // Refuse attempts to change the GitHub login through the account endpoint, with a clear
    // error instead of a silent no-op.
    before: createAuthMiddleware(async (ctx) => {
      if (ctx.path === "/update-user" && ctx.body && "githubLogin" in ctx.body) {
        throw new APIError("BAD_REQUEST", { message: "The GitHub login can't be changed." });
      }
    }),
  },
  databaseHooks: {
    user: {
      update: {
        // githubLogin is fixed at creation (the API grants admin roles by it). Better Auth
        // merges a hook's returned data into the update, so leaving the key out wouldn't
        // remove it: cancel any update that carries it. Defence in depth behind hooks.before.
        before: async (data) => ("githubLogin" in data ? false : undefined),
      },
    },
    session: {
      create: {
        // Every sign-in (the first one included) tells the API the user exists: it creates
        // the profile idempotently and keeps admin roles (ADMIN_GITHUB_LOGINS) in step.
        after: async (session, ctx) => {
          const user = await ctx?.context.internalAdapter.findUserById(session.userId);
          if (user) await syncProfile(user);
        },
      },
    },
  },
  // nextCookies must be last: it lets server actions set auth cookies.
  plugins: [...config.plugins, nextCookies()],
});

export type Session = typeof auth.$Infer.Session;

/** The current session (once per request), or null. Reads cookies, so the route is dynamic. */
export const getSession = cache(async (): Promise<Session | null> => {
  return auth.api.getSession({ headers: await headers() });
});

/** A short-lived JWT for calling the API as the current user, or null when signed out. */
export const getApiToken = cache(async (): Promise<string | null> => {
  const session = await getSession();
  if (!session) return null;
  const { token } = await auth.api.getToken({ headers: await headers() });
  return token;
});

/** The session, or a redirect to sign-in that returns to `next` (pages that need an account). */
export async function requireSession(next: string): Promise<Session> {
  const session = await getSession();
  if (!session) redirect(`/sign-in?next=${encodeURIComponent(next)}`);
  return session;
}
