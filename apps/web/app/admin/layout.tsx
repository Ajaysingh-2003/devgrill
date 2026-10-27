import Link from "next/link";
import { Suspense } from "react";
import { adminMe } from "@devgrill/api-client";
import { Wordmark } from "@devgrill/ui/icons";
import { ConsoleNav, type NavItem } from "@/components/admin/console-nav";
import { api } from "@/lib/api";

/** Each section and the permission that opens it (devgrill.domain.admin). */
const SECTIONS: (NavItem & { needs: string })[] = [
  { href: "/admin", label: "Scenarios", needs: "view_console" },
  { href: "/admin/analytics", label: "Analytics", needs: "view_console" },
  { href: "/admin/ai", label: "AI and fixes", needs: "review_fixes" },
  { href: "/admin/users", label: "Users", needs: "manage_users" },
  { href: "/admin/audit", label: "Audit log", needs: "view_audit" },
];

async function Nav() {
  const { data } = await adminMe({ client: await api() });
  if (!data) return null;
  const allowed = new Set(data.permissions);
  return <ConsoleNav items={SECTIONS.filter((s) => allowed.has(s.needs))} />;
}

/** T10 Admin: the content console (dense Control Room). Pages check access themselves. */
export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <>
      <header className="border-b border-border">
        <div className="flex h-12 items-center gap-4 px-4">
          <Link href="/drills" aria-label="DevGrill home" className="rounded-sm">
            <Wordmark />
          </Link>
          <span className="text-label font-semibold text-fg-muted">Content console</span>
          <Suspense fallback={null}>
            <Nav />
          </Suspense>
        </div>
      </header>
      <main id="main" className="flex flex-col gap-4 p-4">
        {children}
      </main>
    </>
  );
}
