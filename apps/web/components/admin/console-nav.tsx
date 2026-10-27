"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@devgrill/ui/lib/utils";

export type NavItem = { href: string; label: string };

/** The console's sections: only those the caller's roles open (GET /v1/admin/me). */
export function ConsoleNav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav aria-label="Console" className="flex items-center gap-1 overflow-x-auto">
      {items.map((item) => {
        const current = item.href === "/admin" ? path === "/admin" : path.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "rounded-sm px-2.5 py-1.5 text-label font-medium whitespace-nowrap",
              current ? "bg-raised text-fg" : "text-fg-muted hover:bg-raised hover:text-fg",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
