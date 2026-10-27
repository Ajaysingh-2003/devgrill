"use server";

import { patchMe, setLeave, type Prefs, type PrefsPatch } from "@devgrill/api-client";
import { ApiError, api, unwrap } from "@/lib/api";

/** Show or hide the public profile (/u/handle). */
export async function saveVisibility(isPublic: boolean): Promise<boolean> {
  const me = await unwrap(patchMe({ client: await api(), body: { is_public: isPublic } }));
  return me.is_public;
}

/** Save preference changes to the profile (merged server-side; omitted keys are kept). */
export async function savePrefs(patch: PrefsPatch): Promise<Prefs> {
  const me = await unwrap(patchMe({ client: await api(), body: { prefs: patch } }));
  return me.prefs;
}

/** Replace the on-call leave booked from today on; returns what is booked now. */
export async function saveLeave(days: string[]): Promise<string[]> {
  try {
    return (await unwrap(setLeave({ client: await api(), body: { days } }))).days;
  } catch (err) {
    // Server actions lose error classes on the way to the client: send the API's own words.
    throw new Error(err instanceof ApiError ? err.message : "Couldn’t save that. Try again.");
  }
}
