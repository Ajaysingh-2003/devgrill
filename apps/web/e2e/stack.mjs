// Shared settings for the end-to-end stack: its own ports, database and Valkey db, and a
// mock GitHub, so e2e runs never touch dev data, a running dev server or real GitHub.
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseEnv } from "node:util";

// Playwright compiles this to CommonJS (no import.meta), so locate the repo from the working
// directory: every entry point (pnpm e2e, playwright test) runs in apps/web.
export const ROOT = resolve(process.cwd(), "..", "..");
if (!existsSync(join(ROOT, "pnpm-workspace.yaml"))) {
  throw new Error(`e2e must run from apps/web (repo root not found at ${ROOT})`);
}
export const WEB_PORT = 3100;
export const API_PORT = 8800;
export const IDP_PORT = 3999;
export const WEB_URL = `http://localhost:${WEB_PORT}`;
// IPv4 explicitly: uvicorn binds 127.0.0.1, and Node may try ::1 first for "localhost".
export const API_URL = `http://127.0.0.1:${API_PORT}`;
export const IDP_URL = `http://localhost:${IDP_PORT}`;
export const ADMIN_LOGIN = "octo-admin";

/** The repo .env (if any) under the real environment, like next.config.ts does. */
function baseEnv() {
  const file = join(ROOT, ".env");
  const fromFile = existsSync(file) ? parseEnv(readFileSync(file, "utf8")) : {};
  return { ...fromFile, ...process.env };
}

const base = baseEnv();
const dbUrl = (base.DATABASE_URL ?? "postgresql+asyncpg://devgrill:devgrill@localhost:5432/devgrill").replace(
  /\/[^/?]+(\?|$)/,
  "/devgrill_e2e$1",
);
const valkeyUrl = (base.VALKEY_URL ?? "redis://localhost:6379/0").replace(/\/\d+$/, "/14");

export const STACK_ENV = {
  ...base,
  DEVGRILL_ENV: "test",
  LOG_LEVEL: "WARNING",
  DATABASE_URL: dbUrl,
  VALKEY_URL: valkeyUrl,
  API_PORT: String(API_PORT),
  API_CORS_ORIGINS: WEB_URL,
  API_INTERNAL_URL: API_URL,
  BETTER_AUTH_URL: WEB_URL,
  AUTH_ISSUER: WEB_URL,
  AUTH_JWKS_URL: `${WEB_URL}/api/auth/jwks`,
  GITHUB_OAUTH_URL: IDP_URL,
  GITHUB_API_URL: IDP_URL,
  GITHUB_CLIENT_ID: "e2e-client",
  GITHUB_CLIENT_SECRET: "e2e-secret",
  ADMIN_GITHUB_LOGINS: ADMIN_LOGIN,
  // Check every request against the session table so expiry tests see changes at once.
  AUTH_COOKIE_CACHE_SECONDS: "0",
  // Every test browser signs in from 127.0.0.1; Better Auth's per-IP sign-in limit (3 per 10 s)
  // would throttle parallel tests. Production keeps it on.
  AUTH_RATE_LIMIT: "off",
  RATE_LIMIT_DEFAULT: "5000",
  MOCK_GITHUB_PORT: String(IDP_PORT),
};

/** The project's virtualenv Python (deps are synced by `uv sync`; no uv needed on PATH). */
export const PYTHON = join(ROOT, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

/** node-postgres URL for the e2e database (SQLAlchemy URLs carry a driver suffix). */
export const PG_URL = dbUrl.replace(/^postgresql\+\w+:/, "postgresql:");
