import { BRAND } from "@devgrill/config/brand";

const LOCAL_LINKS = [
  { label: "API docs", href: "http://localhost:8000/docs", note: "FastAPI · OpenAPI" },
  { label: "API readiness", href: "http://localhost:8000/readyz", note: "Postgres · Valkey · Temporal" },
  { label: "Temporal UI", href: "http://localhost:8233", note: "Workflows" },
  { label: "Mailpit", href: "http://localhost:8025", note: "Local email" },
] as const;

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-10 px-6 py-24">
      <header className="flex flex-col gap-3">
        <p className="font-mono text-xs tracking-wide text-subtle uppercase">Phase 0 · scaffold</p>
        <h1 className="text-4xl font-semibold tracking-tight">{BRAND.name}</h1>
        <p className="text-lg text-muted">{BRAND.tagline}</p>
      </header>

      <section aria-labelledby="local-services" className="flex flex-col gap-3">
        <h2 id="local-services" className="text-sm font-semibold text-muted">
          Local services
        </h2>
        <ul className="grid gap-2 sm:grid-cols-2">
          {LOCAL_LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="flex flex-col rounded-md border border-border bg-surface px-4 py-3 transition-colors hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                <span className="font-medium text-brand-text">{link.label}</span>
                <span className="font-mono text-xs text-subtle">{link.note}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
