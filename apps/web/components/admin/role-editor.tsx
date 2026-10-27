"use client";

import { adminSetRoles, type RolesIn } from "@devgrill/api-client";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

const ROLES = ["author", "reviewer", "admin"] as const;

/** Grant or remove console roles (every change is audit-logged). */
export function RoleEditor({ userId, handle, roles }: { userId: string; handle: string; roles: string[] }) {
  const router = useRouter();
  const [held, setHeld] = useState(new Set(roles.filter((r) => r !== "user")));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const legend = useId();
  const changed = ROLES.some((r) => held.has(r) !== roles.includes(r));

  async function save() {
    setBusy(true);
    setMessage("");
    try {
      await call(
        adminSetRoles({
          client: browserApi(),
          path: { user_id: userId },
          body: { roles: [...held] as RolesIn["roles"] },
        }),
      );
      setMessage("Saved.");
      router.refresh();
    } catch (err) {
      setMessage(err instanceof ProblemError ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <fieldset aria-labelledby={legend} className="flex flex-wrap items-center gap-3">
      <legend id={legend} className="sr-only">
        Roles for {handle}
      </legend>
      {ROLES.map((role) => (
        <label key={role} className="inline-flex items-center gap-1.5 text-label text-fg">
          <input
            type="checkbox"
            checked={held.has(role)}
            onChange={(e) =>
              setHeld((s) => {
                const next = new Set(s);
                if (e.target.checked) next.add(role);
                else next.delete(role);
                return next;
              })
            }
            className="size-4 accent-brand"
          />
          {role}
        </label>
      ))}
      <button
        type="button"
        disabled={!changed || busy}
        onClick={() => void save()}
        className="h-8 rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised disabled:opacity-50"
      >
        Save roles
      </button>
      <span role="status" className="text-caption text-fg-muted">
        {message}
      </span>
    </fieldset>
  );
}
