import Link from "next/link";
import { SearchX } from "lucide-react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";

/** T11: 404. */
export default function NotFound() {
  return (
    <main id="main" className="grid min-h-dvh place-items-center px-4">
      <EmptyState
        icon={SearchX}
        title="This page isn't on the map"
        action={
          <Link
            href="/drills"
            className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
          >
            Go to the drills
          </Link>
        }
      >
        The link may be old, or the scenario was retired. Everything current is in the drills.
      </EmptyState>
    </main>
  );
}
