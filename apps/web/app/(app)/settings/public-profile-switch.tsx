"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Switch } from "@devgrill/ui/components/ui/switch";
import { saveVisibility } from "./actions";

export function PublicProfileSwitch({ initial, handle }: { initial: boolean; handle: string }) {
  const [on, setOn] = useState(initial);
  const save = useMutation({
    mutationFn: (value: boolean) => saveVisibility(value),
    onSuccess: (value) => setOn(value),
    onError: (_error, value) => {
      setOn(!value); // roll back the optimistic change
      toast.error("Couldn’t save that. Try again.");
    },
  });
  return (
    <div className="flex flex-col gap-2">
      <label className="flex w-fit items-center gap-3 text-body text-fg">
        <Switch
          aria-labelledby="public-profile"
          checked={on}
          disabled={save.isPending}
          onCheckedChange={(value) => {
            setOn(value);
            save.mutate(value);
          }}
        />
        {on ? "Public" : "Only you"}
      </label>
      <p className="text-label text-fg-subtle">
        {on ? `Anyone with the link can see /u/${handle}.` : `/u/${handle} is visible only to you.`}
      </p>
    </div>
  );
}
