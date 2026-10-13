"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useTheme, type MotionPreference, type ThemePreference } from "@devgrill/ui/theme";
import { savePrefs } from "@/app/(app)/settings/actions";

type Saved = { theme?: ThemePreference; motion?: MotionPreference };

/**
 * Keeps theme and motion in step between this device and the signed-in user's profile.
 *
 * - On load the profile wins: a new browser adopts the saved preferences.
 * - After that, any change (settings, the top bar, the command palette) is saved.
 */
export function PrefsSync({ theme, motion }: Saved) {
  const local = useTheme();
  const saved = useRef<Saved>({ theme, motion });
  const adopted = useRef(false);
  const save = useMutation({
    mutationFn: savePrefs,
    onSuccess: (prefs) => {
      saved.current = { theme: prefs.theme, motion: prefs.motion };
    },
    onError: () => toast.error("Couldn’t save your preference. It still applies on this device."),
  });

  // Adopt the profile's preferences once.
  useEffect(() => {
    if (adopted.current) return;
    adopted.current = true;
    if (theme && theme !== local.theme) local.setTheme(theme);
    if (motion && motion !== local.motion) local.setMotion(motion);
  }, [theme, motion, local]);

  // Save later changes. Skips the mount run: it happens in the same commit as the adoption
  // above, before the adopted values reach state, and would save the device's old values.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const patch: { theme?: ThemePreference; motion?: MotionPreference } = {};
    if (saved.current.theme && local.theme !== saved.current.theme) patch.theme = local.theme;
    if (saved.current.motion && local.motion !== saved.current.motion) patch.motion = local.motion;
    if (Object.keys(patch).length) {
      saved.current = { ...saved.current, ...patch };
      save.mutate(patch);
    }
    // `save` is stable enough; re-running on it would double-save.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local.theme, local.motion]);

  return null;
}
