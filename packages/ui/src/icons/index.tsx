import { Cog, Database, Network, Rows3, Server, Zap, type LucideProps } from "lucide-react";
import type { SVGProps } from "react";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * DevGrill mark: a grill grate whose bars shorten like a severity ladder; the top bar
 * carries the heat (brand colour). Uses currentColor for the cool bars so it inherits text colour.
 */
export function DevGrillMark({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={cn("size-6", className)} {...props}>
      <rect x="2" y="3.5" width="20" height="3" rx="1.5" fill="var(--brand)" />
      <rect x="2" y="8.5" width="16" height="3" rx="1.5" fill="currentColor" />
      <rect x="2" y="13.5" width="12" height="3" rx="1.5" fill="currentColor" opacity="0.72" />
      <rect x="2" y="18.5" width="8" height="3" rx="1.5" fill="currentColor" opacity="0.48" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-fg", className)}>
      <DevGrillMark className="size-5" />
      <span className="font-sans text-heading-md font-semibold tracking-tight">DevGrill</span>
    </span>
  );
}

export type Severity = 1 | 2 | 3 | 4;

/**
 * Severity ladder glyph: filled diamonds = severity. SEV1 fills all four.
 * Decorative by default; always pair with a text label (WCAG 1.4.1).
 */
export function SevGlyph({ sev, className, ...props }: { sev: Severity } & SVGProps<SVGSVGElement>) {
  const filled = 5 - sev;
  return (
    <svg viewBox="0 0 40 10" aria-hidden="true" className={cn("h-2.5 w-10 shrink-0", className)} {...props}>
      {[0, 1, 2, 3].map((i) => {
        const cx = 5 + i * 10;
        const d = `M${cx} 1 L${cx + 4} 5 L${cx} 9 L${cx - 4} 5 Z`;
        return i < filled ? (
          <path key={i} d={d} fill="currentColor" />
        ) : (
          <path key={i} d={d} fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.55" />
        );
      })}
    </svg>
  );
}

export type ServiceKind = "api" | "worker" | "db" | "cache" | "queue" | "lb";

const SERVICE_ICONS: Record<ServiceKind, (p: LucideProps) => React.ReactNode> = {
  api: (p) => <Server {...p} />,
  worker: (p) => <Cog {...p} />,
  db: (p) => <Database {...p} />,
  cache: (p) => <Zap {...p} />,
  queue: (p) => <Rows3 {...p} />,
  lb: (p) => <Network {...p} />,
};

export const SERVICE_LABELS: Record<ServiceKind, string> = {
  api: "API",
  worker: "Worker",
  db: "Database",
  cache: "Cache",
  queue: "Queue",
  lb: "Load balancer",
};

export function ServiceIcon({ kind, className, ...props }: { kind: ServiceKind } & LucideProps) {
  const Icon = SERVICE_ICONS[kind];
  return <Icon strokeWidth={1.5} aria-hidden="true" className={cn("size-4", className)} {...props} />;
}
