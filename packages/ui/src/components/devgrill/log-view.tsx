import { cn } from "@devgrill/ui/lib/utils";

export type LogLevel = "error" | "warn" | "info" | "debug";
export type LogLine = { id: string; ts: string; level: LogLevel; service: string; message: string };

const LEVEL: Record<LogLevel, { label: string; tone: string }> = {
  error: { label: "ERROR", tone: "text-danger-text" },
  warn: { label: "WARN", tone: "text-warning-text" },
  info: { label: "INFO", tone: "text-info-text" },
  debug: { label: "DEBUG", tone: "text-fg-subtle" },
};

/**
 * Structured log lines. Phase 1 renders a static list; phase 4 adds virtualisation, the query
 * bar, pause-on-hover and the "N new lines" pill. Log lines never animate.
 */
export function LogView({
  lines,
  label = "Logs",
  className,
}: {
  lines: LogLine[];
  label?: string;
  className?: string;
}) {
  return (
    <div role="log" aria-label={label} className={cn("overflow-x-auto font-mono text-mono", className)}>
      <table className="w-full min-w-[36rem] border-collapse">
        {/* Visually the columns are self-evident; screen readers still get headers per cell. */}
        <thead className="sr-only">
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Level</th>
            <th scope="col">Service</th>
            <th scope="col">Message</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id} className="align-top hover:bg-raised">
              <td className="py-0.5 pr-3 pl-3 whitespace-nowrap text-fg-subtle tabular-nums">{line.ts}</td>
              <td className={cn("py-0.5 pr-3 font-semibold whitespace-nowrap", LEVEL[line.level].tone)}>
                {LEVEL[line.level].label}
              </td>
              <td className="py-0.5 pr-3 whitespace-nowrap text-fg-muted">{line.service}</td>
              <td className="py-0.5 pr-3 wrap-anywhere text-fg">{line.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
