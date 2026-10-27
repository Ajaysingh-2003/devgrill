import type { ShareCardOut } from "@devgrill/api-client";
import { sevNumber } from "./format";

/** "11:42" (or "1:02:05" past an hour) for a resolve time in seconds. */
export function stopwatch(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

/** "Daily drill, 27 Oct" or the scenario's own name: what the card is about. */
export function shareHeading(card: ShareCardOut): string {
  if (!card.daily_on) return card.scenario_title;
  const day = new Date(`${card.daily_on}T00:00:00Z`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  return `Daily drill, ${day}`;
}

/** The one-line, spoiler-free result: "SEV2 fixed in 11:42 with 1 hint". */
export function shareLine(card: ShareCardOut): string {
  const hints =
    card.hints_used === 0 ? "no hints" : `${card.hints_used} hint${card.hints_used === 1 ? "" : "s"}`;
  return `SEV${sevNumber(card.difficulty)} fixed in ${stopwatch(card.resolved_in_s)} with ${hints}`;
}
