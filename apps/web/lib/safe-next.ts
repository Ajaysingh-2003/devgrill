/**
 * Where to send someone after sign-in. Only same-site paths are allowed: "/drills" yes,
 * "//evil.example" or "https://evil.example" no (open-redirect protection).
 */
export function safeNext(value: string | string[] | undefined, fallback = "/drills"): string {
  const next = Array.isArray(value) ? value[0] : value;
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}
