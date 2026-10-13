/**
 * Better Auth options shared by the web app (lib/auth.ts) and the migration script
 * (scripts/auth-migrate.mts). Package imports only, so plain Node can load it.
 *
 * - Data lives in Postgres schema `auth` (ADR 011); ids are UUIDs so the API can use them.
 * - GitHub is a generic OAuth provider with configurable endpoints: real GitHub locally,
 *   a mock IdP in tests, one code path (ADR 011).
 * - The JWT plugin signs short-lived EdDSA tokens for the API (ADR 005), rotating keys.
 */
import type { BetterAuthOptions } from "better-auth";
import { genericOAuth } from "better-auth/plugins/generic-oauth";
import { jwt } from "better-auth/plugins/jwt";
import { Pool } from "pg";

export const AUTH_SCHEMA = "auth";
export const API_AUDIENCE = process.env.AUTH_AUDIENCE ?? "devgrill-api";

const env = (name: string, fallback = "") => process.env[name] ?? fallback;

/** SQLAlchemy URLs carry a driver ("postgresql+asyncpg://"); node-postgres wants plain. */
export function authDatabaseUrl(): string {
  return env("DATABASE_URL", "postgresql://devgrill:devgrill@localhost:5432/devgrill").replace(
    /^postgresql\+\w+:/,
    "postgresql:",
  );
}

type GitHubProfile = {
  id: number;
  login: string;
  name: string | null;
  email: string | null;
  avatar_url: string | null;
};
type GitHubEmail = { email: string; primary: boolean; verified: boolean };

async function githubUserInfo(accessToken: string) {
  const api = env("GITHUB_API_URL", "https://api.github.com");
  const headers = {
    Authorization: `Bearer ${accessToken}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "devgrill",
  };
  const res = await fetch(`${api}/user`, { headers });
  if (!res.ok) return null;
  const profile = (await res.json()) as GitHubProfile;
  let email = profile.email;
  let emailVerified = false;
  const emailsRes = await fetch(`${api}/user/emails`, { headers });
  if (emailsRes.ok) {
    const emails = (await emailsRes.json()) as GitHubEmail[];
    const chosen = emails.find((e) => e.email === email) ?? emails.find((e) => e.primary) ?? emails[0];
    email = email ?? chosen?.email ?? null;
    emailVerified = Boolean(chosen?.verified && chosen.email === email);
  }
  return {
    id: String(profile.id),
    name: profile.name || profile.login,
    email: email ?? undefined,
    image: profile.avatar_url ?? undefined,
    emailVerified,
    login: profile.login,
  };
}

export function authConfig() {
  const baseURL = env("BETTER_AUTH_URL", "http://localhost:3000");
  const oauthBase = env("GITHUB_OAUTH_URL", "https://github.com");
  return {
    appName: "DevGrill",
    baseURL,
    secret: env("BETTER_AUTH_SECRET"),
    trustedOrigins: [baseURL],
    // Better Auth's limiter (sign-in: 3 per 10 s per IP) stays on. Only the e2e stack, where
    // every browser shares 127.0.0.1, turns it off (AUTH_RATE_LIMIT=off in e2e/stack.mjs).
    rateLimit: { enabled: env("AUTH_RATE_LIMIT", "on") !== "off" },
    database: new Pool({
      connectionString: authDatabaseUrl(),
      options: `-c search_path=${AUTH_SCHEMA}`,
      max: 10,
      // Keep connections warm: node-postgres closes idle ones after 10 s by default, and the
      // reconnect churn stalls behind Docker Desktop's port proxy (and costs a TLS handshake
      // to a managed database later).
      idleTimeoutMillis: 5 * 60_000,
      keepAlive: true,
      // Fail a stuck connect after 10 s instead of the OS default (~21 s on Windows).
      connectionTimeoutMillis: 10_000,
    }),
    advanced: {
      cookiePrefix: "devgrill",
      database: { generateId: "uuid" },
    },
    user: {
      additionalFields: {
        // Set from the GitHub profile when the account is created (input: false would also
        // drop it there). Never changeable afterwards: see the user.update hook in lib/auth.ts,
        // because the API grants admin roles by GitHub login.
        githubLogin: { type: "string", required: false, input: true },
      },
    },
    // GitHub is the only way in: no email/password sign-up that could set githubLogin.
    emailAndPassword: { enabled: false },
    session: {
      expiresIn: 60 * 60 * 24 * 30, // 30 days
      updateAge: 60 * 60 * 24, // refresh the expiry at most daily
      // Signed session data cached in a cookie for 5 minutes saves a DB read per request; a
      // revoked session can therefore live up to that long. Tests set 0 to check expiry.
      cookieCache: {
        enabled: Number(env("AUTH_COOKIE_CACHE_SECONDS", "300")) > 0,
        maxAge: Number(env("AUTH_COOKIE_CACHE_SECONDS", "300")),
      },
    },
    plugins: [
      genericOAuth({
        config: [
          {
            // Provider id "github" keeps the callback at /api/auth/callback/github.
            providerId: "github",
            name: "GitHub",
            clientId: env("GITHUB_CLIENT_ID"),
            clientSecret: env("GITHUB_CLIENT_SECRET"),
            authorizationUrl: `${oauthBase}/login/oauth/authorize`,
            tokenUrl: `${oauthBase}/login/oauth/access_token`,
            scopes: ["read:user", "user:email"],
            getUserInfo: (tokens) => githubUserInfo(tokens.accessToken ?? ""),
            mapProfileToUser: (profile) => ({ githubLogin: String(profile.login ?? "") }),
          },
        ],
      }),
      jwt({
        jwt: {
          issuer: env("AUTH_ISSUER", baseURL),
          audience: API_AUDIENCE,
          expirationTime: "15m",
          definePayload: ({ user }) => ({
            name: user.name,
            email: user.email,
            image: user.image ?? undefined,
            login: (user as { githubLogin?: string }).githubLogin ?? undefined,
          }),
        },
        jwks: {
          keyPairConfig: { alg: "EdDSA", crv: "Ed25519" },
          // Rotate monthly; old keys stay published for a day (tokens live 15 minutes).
          rotationInterval: 60 * 60 * 24 * 30,
          gracePeriod: 60 * 60 * 24,
        },
      }),
    ],
  } satisfies BetterAuthOptions;
}
