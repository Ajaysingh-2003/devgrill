"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authClient } from "@/lib/auth-client";

/** Ends the session (the same as the avatar menu's "Sign out") and goes home. */
export function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await authClient.signOut();
        router.push("/");
        router.refresh();
      }}
      className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised disabled:opacity-60"
    >
      <LogOut className="size-4" aria-hidden="true" />
      {busy ? "Signing out…" : "Sign out"}
    </button>
  );
}
