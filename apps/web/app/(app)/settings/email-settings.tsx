"use client";

import type { PrefsPatch } from "@devgrill/api-client";
import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Switch } from "@devgrill/ui/components/ui/switch";
import { savePrefs } from "./actions";

type Hour = NonNullable<PrefsPatch["digest_hour"]>;
const HOURS: Hour[] = [8, 9, 13, 18, 21];

/** The daily email: opt-in, a send time to pick, quiet hours and the one-a-day cap are fixed. */
export function EmailSettings({
  initialOn,
  initialHour,
  hasEmail,
}: {
  initialOn: boolean;
  initialHour: Hour;
  hasEmail: boolean;
}) {
  const [on, setOn] = useState(initialOn);
  const [hour, setHour] = useState(initialHour);
  const hourId = useId();
  const save = useMutation({
    mutationFn: (patch: PrefsPatch) => savePrefs(patch),
    onSuccess: (prefs) => {
      setOn(prefs.email_digest ?? false);
      setHour((prefs.digest_hour ?? 9) as Hour);
    },
    onError: () => {
      setOn(initialOn);
      setHour(initialHour);
      toast.error("Couldn’t save that. Try again.");
    },
  });

  if (!hasEmail) {
    return (
      <p className="text-body text-fg-muted">
        GitHub didn’t share an email address with us. Make one public on GitHub, sign in again, and this turns
        on.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <label className="flex w-fit items-center gap-3 text-body text-fg">
        <Switch
          aria-labelledby="daily-email"
          checked={on}
          disabled={save.isPending}
          onCheckedChange={(value) => {
            setOn(value);
            save.mutate({ email_digest: value });
          }}
        />
        {on ? "On" : "Off"}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={hourId} className="text-body text-fg">
          Send it at
        </label>
        <select
          id={hourId}
          value={hour}
          disabled={!on || save.isPending}
          onChange={(e) => {
            const next = Number(e.target.value) as Hour;
            setHour(next);
            save.mutate({ digest_hour: next });
          }}
          className="h-9 rounded-sm border border-border-input bg-surface px-2 text-body text-fg disabled:opacity-50"
        >
          {HOURS.map((h) => (
            <option key={h} value={h}>
              {String(h).padStart(2, "0")}:00
            </option>
          ))}
        </select>
        <span className="text-label text-fg-subtle">your time</span>
      </div>
    </div>
  );
}
