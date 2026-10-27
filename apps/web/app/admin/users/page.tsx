import type { Metadata } from "next";
import { Suspense } from "react";
import { adminMe, adminUsers } from "@devgrill/api-client";
import { refusal } from "@/components/admin/forbidden";
import { RoleEditor } from "@/components/admin/role-editor";
import { PageSkeleton } from "@/components/page-skeleton";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Users" };

async function Results({ searchParams }: { searchParams: PageProps<"/admin/users">["searchParams"] }) {
  const raw = (await searchParams).q;
  const q = (Array.isArray(raw) ? raw[0] : raw)?.trim() ?? "";
  const client = await api();
  if (q.length < 2) {
    const { data, response } = await adminMe({ client });
    if (!data || !data.permissions.includes("manage_users")) {
      return refusal(data ? new Response(null, { status: 403 }) : response, "User lookup");
    }
    return <p className="text-body text-fg-muted">Search by handle or name (two letters or more).</p>;
  }
  const { data, response } = await adminUsers({ client, query: { q } });
  if (!data) return refusal(response, "User lookup");
  if (!data.length) return <p className="text-body text-fg-muted">Nobody matches “{q}”.</p>;
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-surface">
      <table className="w-full min-w-[60rem] text-left text-body">
        <caption className="sr-only">Users matching {q}</caption>
        <thead className="border-b border-border text-caption text-fg-subtle">
          <tr>
            {["Handle", "Name", "Plan", "Runs", "Last active", "Joined", "Roles"].map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((u) => (
            <tr key={u.user_id} className="border-b border-border last:border-b-0">
              <th scope="row" className="px-3 py-2 font-mono text-mono font-medium text-fg">
                {u.handle}
              </th>
              <td className="px-3 py-2 text-fg-muted">{u.display_name}</td>
              <td className="px-3 py-2 text-fg-muted">{u.plan}</td>
              <td className="px-3 py-2 font-mono text-mono tabular-nums">{u.attempts}</td>
              <td className="px-3 py-2 text-fg-muted">{u.last_active ?? "–"}</td>
              <td className="px-3 py-2 text-fg-muted">
                <time dateTime={u.created_at}>{u.created_at.slice(0, 10)}</time>
              </td>
              <td className="px-3 py-2">
                <RoleEditor userId={u.user_id} handle={u.handle} roles={u.roles} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Support lookup and roles (admins only). */
export default function UsersPage({ searchParams }: PageProps<"/admin/users">) {
  return (
    <>
      <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Users</h1>
      <form role="search" className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-label text-fg-muted">
          Handle or name
          <input
            name="q"
            type="search"
            minLength={2}
            maxLength={40}
            autoComplete="off"
            spellCheck={false}
            className="h-9 w-64 rounded-sm border border-border-input bg-surface px-2 text-body text-fg"
          />
        </label>
        <button
          type="submit"
          className="h-9 rounded-sm border border-border-strong px-3 text-label font-medium text-fg hover:bg-raised"
        >
          Search
        </button>
      </form>
      <Suspense fallback={<PageSkeleton label="Searching" />}>
        <Results searchParams={searchParams} />
      </Suspense>
    </>
  );
}
