import "server-only";
import { cache } from "react";
import { getMe, myStreak, type Prefs } from "@devgrill/api-client";
import { api } from "./api";
import { getSession } from "./auth";

/** What the shell needs to know about the signed-in user. */
export type Viewer = {
  handle: string;
  displayName: string;
  avatarUrl: string | null;
  roles: string[];
  streak: number;
  prefs: Prefs;
};

/**
 * The signed-in user's profile summary, or null when signed out. If the API is unreachable
 * the shell still renders: the user is treated as signed in without profile details.
 */
export const getViewer = cache(async (): Promise<Viewer | null> => {
  const session = await getSession();
  if (!session) return null;
  const client = await api();
  const [me, streak] = await Promise.all([getMe({ client }), myStreak({ client })]);
  if (!me.data) {
    return {
      handle: "",
      displayName: session.user.name,
      avatarUrl: session.user.image ?? null,
      roles: [],
      streak: 0,
      prefs: {
        theme: "system",
        motion: "system",
        sounds: false,
        pro_mode: false,
        streak_mode: "daily",
        timezone: "Asia/Kolkata",
      },
    };
  }
  return {
    handle: me.data.handle,
    displayName: me.data.display_name,
    avatarUrl: me.data.avatar_url,
    roles: me.data.roles,
    streak: streak.data?.current ?? 0,
    prefs: me.data.prefs,
  };
});
