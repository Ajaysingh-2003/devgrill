import "server-only";
import { createHmac } from "node:crypto";

/**
 * Server-to-server calls to the API, signed with INTERNAL_HMAC_SECRET.
 * Mirrors apps/api/src/devgrill_api/auth/internal.py: HMAC-SHA256 over `${timestamp}.${body}`.
 */
export async function callInternal(path: string, payload: unknown): Promise<Response> {
  const secret = process.env.INTERNAL_HMAC_SECRET ?? "";
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac("sha256", secret).update(`${timestamp}.${body}`).digest("hex");
  return fetch(`${base}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-devgrill-timestamp": String(timestamp),
      "x-devgrill-signature": signature,
    },
    body,
    cache: "no-store",
  });
}

type HookUser = { id: string; name?: string | null; email?: string | null; image?: string | null };

/**
 * Tell the API a user exists (creates the profile; applies configured admin roles).
 * Never blocks sign-in: the API also creates the profile on the first authenticated call.
 */
export async function syncProfile(user: HookUser & { githubLogin?: string | null }): Promise<void> {
  try {
    const res = await callInternal("/internal/profiles", {
      user_id: user.id,
      login: user.githubLogin || null,
      name: user.name || null,
      email: user.email || null,
      image: user.image || null,
    });
    if (!res.ok) console.warn(`profile sync failed: ${res.status}`);
  } catch (error) {
    console.warn("profile sync failed", error);
  }
}
