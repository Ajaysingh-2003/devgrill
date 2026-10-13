"use server";

import { patchMe, type Prefs, type PrefsPatch } from "@devgrill/api-client";
import { api, unwrap } from "@/lib/api";

/** Save preference changes to the profile (merged server-side; omitted keys are kept). */
export async function savePrefs(patch: PrefsPatch): Promise<Prefs> {
  const me = await unwrap(patchMe({ client: await api(), body: { prefs: patch } }));
  return me.prefs;
}
