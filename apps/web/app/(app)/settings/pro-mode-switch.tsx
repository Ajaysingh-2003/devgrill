"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Switch } from "@devgrill/ui/components/ui/switch";
import { savePrefs } from "./actions";

export function ProModeSwitch({ initial }: { initial: boolean }) {
  const [on, setOn] = useState(initial);
  const save = useMutation({
    mutationFn: (value: boolean) => savePrefs({ pro_mode: value }),
    onSuccess: (prefs) => setOn(prefs.pro_mode ?? false),
    onError: (_error, value) => {
      setOn(!value); // roll back the optimistic change
      toast.error("Couldn’t save pro mode. Try again.");
    },
  });
  return (
    <label className="flex w-fit items-center gap-3 text-body text-fg">
      <Switch
        checked={on}
        disabled={save.isPending}
        onCheckedChange={(value) => {
          setOn(value);
          save.mutate(value);
        }}
      />
      {on ? "On" : "Off"}
    </label>
  );
}
