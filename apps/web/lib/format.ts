/** Display formatting. India-first: numbers group as en-IN (12,34,567) for now. */

const counts = new Intl.NumberFormat("en-IN");

export function formatCount(n: number): string {
  return counts.format(n);
}

/** "9h 41m" until `iso`, or "under a minute". */
export function timeLeft(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.floor((new Date(iso).getTime() - now.getTime()) / 60_000));
  if (minutes < 1) return "under a minute";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

/** "October 2026" */
export function monthYear(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric" }).format(new Date(iso));
}
