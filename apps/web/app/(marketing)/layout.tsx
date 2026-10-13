import Link from "next/link";
import { Wordmark } from "@devgrill/ui/icons";
import { fontArcade } from "../fonts";

/** T1 marketing shell: minimal top bar and footer. */
export default function MarketingLayout({ children }: LayoutProps<"/">) {
  return (
    <div className={`${fontArcade.variable} flex min-h-dvh flex-col`}>
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-[75rem] items-center gap-6 px-4 sm:px-6">
          <Link href="/" aria-label="DevGrill home" className="rounded-sm">
            <Wordmark />
          </Link>
          <nav aria-label="Main" className="ml-auto flex items-center gap-1 text-label font-medium">
            <Link href="/drills" className="rounded-sm px-2.5 py-1.5 text-fg-muted hover:text-fg">
              Drills
            </Link>
            <Link href="/sign-in" className="rounded-sm px-2.5 py-1.5 text-fg-muted hover:text-fg">
              Sign in
            </Link>
          </nav>
        </div>
      </header>
      <main id="main">{children}</main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[75rem] flex-wrap items-center justify-between gap-4 px-4 py-8 text-label text-fg-muted sm:px-6">
          <Wordmark className="text-fg-muted" />
          <p>Built for engineers who would rather practise the outage than live it.</p>
        </div>
      </footer>
    </div>
  );
}
