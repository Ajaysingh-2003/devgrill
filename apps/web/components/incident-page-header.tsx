import Link from "next/link";
import { Wordmark } from "@devgrill/ui/icons";

/** Slim header for after-incident pages (debrief, postmortem): no main nav, one way back. */
export function IncidentPageHeader({
  context,
  back,
}: {
  context: string;
  back: { href: string; label: string };
}) {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex h-14 max-w-[72rem] items-center gap-4 px-4 sm:px-6">
        <Link href="/drills" aria-label="DevGrill home" className="rounded-sm">
          <Wordmark />
        </Link>
        <span className="hidden truncate text-label text-fg-muted sm:inline">{context}</span>
        <Link href={back.href} className="ml-auto text-label font-medium text-brand-text hover:underline">
          {back.label}
        </Link>
      </div>
    </header>
  );
}
