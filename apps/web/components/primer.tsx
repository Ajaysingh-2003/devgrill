import { BookOpen } from "lucide-react";
import type { ReactNode } from "react";

/**
 * A topic primer: the small Markdown subset primers are written in (content/primers), rendered
 * without HTML injection: `##`/`###` headings, paragraphs, `-` and `1.` lists, **bold**,
 * `inline code` and fenced code blocks. Anything else shows as plain text.
 */
export function Primer({ markdown, topic }: { markdown: string; topic: string }) {
  const words = markdown.split(/\s+/).length;
  const minutes = Math.max(1, Math.round(words / 200));
  return (
    <details className="group rounded-md border border-border bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-body font-medium text-fg hover:bg-raised [&::-webkit-details-marker]:hidden">
        <BookOpen className="size-4 text-fg-muted" aria-hidden="true" />
        <span>
          Read the primer on {topic.toLowerCase()}
          <span className="ml-2 text-label font-normal text-fg-muted">{minutes} min read</span>
        </span>
      </summary>
      <div className="flex max-w-[44rem] flex-col gap-3 border-t border-border px-4 py-4">
        {blocks(markdown)}
      </div>
    </details>
  );
}

type Block =
  | { kind: "h2" | "h3" | "p"; text: string }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "code"; lang: string; text: string };

function parse(markdown: string): Block[] {
  const out: Block[] = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!;
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const fence = line.match(/^```(\w*)\s*$/);
    if (fence) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^```\s*$/.test(lines[i]!)) body.push(lines[i++]!);
      i += 1; // the closing fence
      out.push({ kind: "code", lang: fence[1] ?? "", text: body.join("\n") });
      continue;
    }
    const heading = line.match(/^(#{2,3})\s+(.*)$/);
    if (heading) {
      out.push({ kind: heading[1] === "##" ? "h2" : "h3", text: heading[2]! });
      i += 1;
      continue;
    }
    const list = line.match(/^(-|\d+\.)\s+/);
    if (list) {
      const ordered = list[1] !== "-";
      const items: string[] = [];
      while (i < lines.length && (ordered ? /^\d+\.\s+/ : /^-\s+/).test(lines[i]!)) {
        let item = lines[i++]!.replace(/^(-|\d+\.)\s+/, "");
        // Wrapped continuation lines belong to the item.
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]!)) item += ` ${lines[i++]!.trim()}`;
        items.push(item);
      }
      out.push({ kind: ordered ? "ol" : "ul", items });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i]!.trim() && !/^(#{2,3}\s|```|-\s|\d+\.\s)/.test(lines[i]!)) {
      para.push(lines[i++]!.trim());
    }
    out.push({ kind: "p", text: para.join(" ") });
  }
  return out;
}

/** **bold** and `code` inside a line, as React nodes (never HTML). */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={i} className="rounded-xs bg-raised px-1 font-mono text-mono-sm">
          {part.slice(1, -1)}
        </code>
      );
    return part;
  });
}

function blocks(markdown: string): ReactNode[] {
  return parse(markdown).map((b, i) => {
    switch (b.kind) {
      case "h2":
        return (
          <h3 key={i} className="mt-2 text-body-lg font-semibold text-fg">
            {inline(b.text)}
          </h3>
        );
      case "h3":
        return (
          <h4 key={i} className="text-body font-semibold text-fg">
            {inline(b.text)}
          </h4>
        );
      case "p":
        return (
          <p key={i} className="text-body text-fg">
            {inline(b.text)}
          </p>
        );
      case "ul":
      case "ol": {
        const List = b.kind === "ul" ? "ul" : "ol";
        return (
          <List
            key={i}
            className={`flex flex-col gap-1 pl-5 text-body text-fg ${b.kind === "ul" ? "list-disc" : "list-decimal"}`}
          >
            {b.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </List>
        );
      }
      case "code":
        return (
          <pre
            key={i}
            tabIndex={0}
            aria-label={b.lang ? `${b.lang} example` : "Example"}
            className="overflow-x-auto rounded-sm border border-border bg-sunken px-3 py-2 font-mono text-mono-sm text-fg"
          >
            <code>{b.text}</code>
          </pre>
        );
    }
  });
}
