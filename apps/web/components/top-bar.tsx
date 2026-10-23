"use client";

import {
  Accessibility,
  CalendarClock,
  Compass,
  LogIn,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Search,
  Settings,
  Sun,
  User,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { CommandPalette, type PaletteCommand } from "@devgrill/ui/components/devgrill/command-palette";
import { Streak } from "@devgrill/ui/components/devgrill/streak";
import { ThemeSwitch } from "@devgrill/ui/components/devgrill/theme-controls";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@devgrill/ui/components/ui/sheet";
import { useIsMac } from "@devgrill/ui/hooks/use-platform";
import { Wordmark } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";
import { useTheme } from "@devgrill/ui/theme";
import { authClient } from "@/lib/auth-client";
import type { Viewer } from "@/lib/viewer";

const NAV = [
  { href: "/drills", label: "Drills", icon: Compass },
  { href: "/daily", label: "Daily drill", icon: CalendarClock },
  { href: "/quickfire", label: "Quick Fire", icon: Zap },
] as const;

/**
 * App shell top bar. `viewer` is undefined while the session loads (the bar renders at once
 * and the account area fills in), null when signed out.
 */
export function TopBar({ viewer }: { viewer: Viewer | null | undefined }) {
  const pathname = usePathname();
  const router = useRouter();
  const { setTheme, setMotion, reducedMotion } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const isMac = useIsMac();

  const commands: PaletteCommand[] = [
    ...NAV.map((n) => ({
      id: n.href,
      group: "Go to",
      label: n.label,
      icon: n.icon,
      onSelect: () => router.push(n.href),
    })),
    viewer
      ? {
          id: "profile",
          group: "Go to",
          label: "Your profile",
          icon: User,
          onSelect: () => router.push(`/u/${viewer.handle}`),
        }
      : {
          id: "sign-in",
          group: "Go to",
          label: "Sign in",
          icon: LogIn,
          onSelect: () => router.push(`/sign-in?next=${encodeURIComponent(pathname)}`),
        },
    {
      id: "settings",
      group: "Go to",
      label: "Settings",
      icon: Settings,
      onSelect: () => router.push("/settings"),
    },
    {
      id: "light",
      group: "Appearance",
      label: "Use light theme",
      icon: Sun,
      onSelect: () => setTheme("light"),
    },
    {
      id: "dark",
      group: "Appearance",
      label: "Use dark theme",
      icon: Moon,
      onSelect: () => setTheme("dark"),
    },
    {
      id: "system",
      group: "Appearance",
      label: "Match device theme",
      icon: Monitor,
      onSelect: () => setTheme("system"),
    },
    {
      id: "motion",
      group: "Appearance",
      label: reducedMotion ? "Allow motion" : "Reduce motion",
      icon: Accessibility,
      onSelect: () => setMotion(reducedMotion ? "full" : "reduce"),
    },
    ...(viewer
      ? [
          {
            id: "sign-out",
            group: "Account",
            label: "Sign out",
            icon: LogOut,
            onSelect: () => void signOut(),
          },
        ]
      : []),
  ];

  async function signOut() {
    await authClient.signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-[var(--z-sticky)] border-b border-border bg-canvas/90 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[75rem] items-center gap-4 px-4 sm:px-6">
        <Link href="/drills" className="rounded-sm" aria-label="DevGrill home">
          <Wordmark />
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-sm px-2.5 py-1.5 text-label font-medium",
                  active ? "bg-raised text-fg" : "text-fg-muted hover:text-fg",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="hidden h-8 items-center gap-2 rounded-sm border border-border-input bg-surface px-2.5 text-label text-fg-subtle hover:text-fg sm:flex"
          >
            <Search className="size-3.5" aria-hidden="true" />
            <span>Search or jump to</span>
            <kbd className="ml-4 font-mono text-mono-sm">{isMac ? "⌘K" : "Ctrl K"}</kbd>
          </button>
          {viewer ? <Streak days={viewer.streak} /> : null}
          <ThemeSwitch className="hidden sm:inline-flex" />
          <AccountButton viewer={viewer} pathname={pathname} />
          <Sheet>
            <SheetTrigger
              render={
                <button
                  type="button"
                  aria-label="Open menu"
                  className="grid size-8 place-items-center rounded-sm text-fg-muted hover:bg-raised md:hidden"
                />
              }
            >
              <Menu className="size-5" aria-hidden="true" />
            </SheetTrigger>
            <SheetContent side="right" className="w-72">
              <SheetTitle className="px-4 pt-4">Menu</SheetTitle>
              <nav aria-label="Main" className="flex flex-col gap-1 p-2">
                {NAV.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-3 rounded-sm px-3 py-2.5 text-body text-fg hover:bg-raised"
                  >
                    <item.icon className="size-4 text-fg-muted" aria-hidden="true" />
                    {item.label}
                  </Link>
                ))}
              </nav>
              <div className="px-4 pt-2">
                <ThemeSwitch />
              </div>
              {viewer ? (
                <div className="px-2 pt-4">
                  <button
                    type="button"
                    onClick={() => void signOut()}
                    className="flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-body text-fg hover:bg-raised"
                  >
                    <LogOut className="size-4 text-fg-muted" aria-hidden="true" />
                    Sign out
                  </button>
                </div>
              ) : null}
            </SheetContent>
          </Sheet>
        </div>
      </div>
      <CommandPalette commands={commands} open={paletteOpen} onOpenChange={setPaletteOpen} />
    </header>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase() || "?";
}

function AccountButton({ viewer, pathname }: { viewer: Viewer | null | undefined; pathname: string }) {
  if (viewer === undefined) {
    // Same footprint as the avatar, so nothing shifts when the session arrives.
    return <span aria-hidden="true" className="size-8 rounded-full bg-raised" />;
  }
  if (viewer === null) {
    return (
      <Link
        href={`/sign-in?next=${encodeURIComponent(pathname)}`}
        className="inline-flex h-8 items-center rounded-sm px-2.5 text-label font-medium text-fg hover:bg-raised"
      >
        Sign in
      </Link>
    );
  }
  const label = initials(viewer.displayName);
  return (
    <Link
      href={viewer.handle ? `/u/${viewer.handle}` : "/settings"}
      aria-label={`Your profile (${label})`}
      className="grid size-8 place-items-center overflow-hidden rounded-full bg-brand-subtle text-label font-semibold text-brand-text"
    >
      {viewer.avatarUrl ? (
        // Plain img: GitHub avatars are tiny and already sized by the CDN.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={viewer.avatarUrl} alt="" width={32} height={32} className="size-8" />
      ) : (
        label
      )}
    </Link>
  );
}
