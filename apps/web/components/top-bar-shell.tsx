import Link from "next/link";
import { Wordmark } from "@devgrill/ui/icons";

/**
 * Static stand-in for the top bar while the session loads. No hooks (it's part of the
 * prerendered shell, which may not read the URL) and the same height, so nothing shifts.
 */
export function TopBarShell() {
  return (
    <header className="sticky top-0 z-[var(--z-sticky)] border-b border-border bg-canvas/90 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[75rem] items-center gap-4 px-4 sm:px-6">
        <Link href="/drills" className="rounded-sm" aria-label="DevGrill home">
          <Wordmark />
        </Link>
        <div className="ml-auto flex items-center gap-2" aria-hidden="true">
          <span className="size-8 rounded-full bg-raised" />
        </div>
      </div>
    </header>
  );
}
