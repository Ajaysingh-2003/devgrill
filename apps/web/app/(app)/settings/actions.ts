"use server";

import { patchMe, type Prefs, type PrefsPatch } from "@devgrill/api-client";
import { api, unwrap } from "@/lib/api";

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
