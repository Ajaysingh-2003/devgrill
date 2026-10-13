/**
 * Fetch shadcn/ui (base-nova, Base UI) component sources from the public registry into
 * src/components/ui, rewriting imports to this package and mapping shadcn's theme classes to
 * DevGrill semantic tokens. We own the copied code afterwards (shadcn's model).
 *
 * Usage: node scripts/fetch-shadcn.ts button dialog ...   (prints npm deps to install)
 * Why not `shadcn add`: on this machine its package-manager step runs through cmd.exe (blocked)
 * and its alias resolution rewrote imports incorrectly (see docs/qc/phase-1.md).
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "src", "components", "ui");
const REGISTRY = "https://ui.shadcn.com/r/styles/base-nova";

// shadcn theme token → DevGrill semantic utility suffix.
const TOKEN_MAP: Record<string, string> = {
  "primary-foreground": "on-brand",
  primary: "brand",
  "secondary-foreground": "fg",
  secondary: "raised",
  "muted-foreground": "fg-muted",
  muted: "raised",
  "accent-foreground": "fg",
  accent: "raised",
  "popover-foreground": "fg",
  popover: "surface",
  "card-foreground": "fg",
  card: "surface",
  "destructive-foreground": "on-danger",
  destructive: "danger-text",
  foreground: "fg",
  background: "surface",
  input: "border-input",
  ring: "focus-ring",
  border: "border",
};
const PREFIXES = [
  "bg",
  "text",
  "border",
  "border-t",
  "border-b",
  "border-l",
  "border-r",
  "border-x",
  "border-y",
  "ring",
  "ring-offset",
  "outline",
  "fill",
  "stroke",
  "divide",
  "placeholder",
  "caret",
  "decoration",
  "from",
  "via",
  "to",
  "shadow",
];

function mapClasses(source: string): string {
  const names = Object.keys(TOKEN_MAP)
    .sort((a, b) => b.length - a.length)
    .join("|");
  const prefixes = PREFIXES.sort((a, b) => b.length - a.length).join("|");
  const re = new RegExp(`(?<![\\w-])(${prefixes})-(${names})(?=[\\s"'\`/\\]):]|$)`, "g");
  return source
    .replace(re, (_m, prefix: string, token: string) => `${prefix}-${TOKEN_MAP[token]}`)
    .replace(
      /var\(--(primary|secondary|muted|accent|foreground|background|destructive|ring|input|border)\)/g,
      (_m, t: string) => {
        const map: Record<string, string> = {
          primary: "--brand",
          secondary: "--raised",
          muted: "--raised",
          accent: "--raised",
          foreground: "--text",
          background: "--surface",
          destructive: "--danger-text",
          ring: "--focus-ring",
          input: "--border-input",
          border: "--border",
        };
        return `var(${map[t]})`;
      },
    );
}

/** shadcn style-hook classes (defined in shadcn's own CSS) → DevGrill equivalents. */
const STYLE_HOOKS: Record<string, string> = {
  "cn-font-heading": "font-sans text-heading-md font-semibold",
  "cn-rtl-flip": "rtl:rotate-180",
  "cn-menu-target": "",
  "cn-menu-translucent": "",
  "cn-toast": "",
};

function mapStyleHooks(source: string): string {
  return source.replace(/\bcn-[a-z-]+\b/g, (hook) => {
    if (!(hook in STYLE_HOOKS)) throw new Error(`Unmapped shadcn style hook: ${hook}`);
    return STYLE_HOOKS[hook]!;
  });
}

/** <IconPlaceholder lucide="X" tabler=… {...rest} /> → <X {...rest} /> with a lucide-react import. */
function replaceIconPlaceholders(source: string): string {
  const used = new Set<string>();
  const out = source.replace(/<IconPlaceholder\b([\s\S]*?)\/>/g, (_m, attrs: string) => {
    const lucide = /\blucide="(\w+)"/.exec(attrs)?.[1];
    if (!lucide) throw new Error("IconPlaceholder without a lucide icon");
    used.add(lucide);
    const rest = attrs.replace(/\s*\b(lucide|tabler|hugeicons|phosphor|remixicon)="[^"]*"/g, "").trim();
    return `<${lucide}${rest ? ` ${rest}` : ""} />`;
  });
  if (!used.size) return out;
  const withoutImport = out.replace(/import \{ IconPlaceholder \} from "[^"]+"\n/, "");
  const lucideImport = `import { ${[...used].sort().join(", ")} } from "lucide-react"\n`;
  // Insert after the last import line.
  const lines = withoutImport.split("\n");
  let lastImport = -1;
  lines.forEach((line, i) => {
    if (line.startsWith("import ")) lastImport = i;
  });
  lines.splice(lastImport + 1, 0, lucideImport.trimEnd());
  return lines.join("\n");
}

function rewriteImports(source: string): string {
  return (
    source
      .replace(/bg-black\/\d+/g, "bg-overlay") // raw-color-ok: maps shadcn colours to tokens
      // Faded text via opacity bypasses the validated contrast tokens.
      .replace(/text-foreground\/\d+/g, "text-muted-foreground")
      .replace(/from "cn"/g, 'from "@devgrill/ui/lib/utils"')
      .replace(/from "@\/registry\/base-nova\/ui\/([\w-]+)"/g, 'from "@devgrill/ui/components/ui/$1"')
      .replace(/from "@\/registry\/base-nova\/lib\/utils"/g, 'from "@devgrill/ui/lib/utils"')
      .replace(/from "@\/registry\/base-nova\/hooks\/([\w-]+)"/g, 'from "@devgrill/ui/hooks/$1"')
  );
}

type RegistryItem = { name: string; dependencies?: string[]; files: { path: string; content: string }[] };

const names = process.argv.slice(2);
if (!names.length) {
  console.error("usage: node scripts/fetch-shadcn.ts <component> [...]");
  process.exit(2);
}
mkdirSync(OUT, { recursive: true });
const deps = new Set<string>();
for (const name of names) {
  const res = await fetch(`${REGISTRY}/${name}.json`);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  const item = (await res.json()) as RegistryItem;
  for (const dep of item.dependencies ?? []) if (dep !== "cn") deps.add(dep);
  for (const file of item.files) {
    const fileName = file.path.split("/").pop()!;
    const header = `// Source: shadcn/ui registry (base-nova) "${name}", adapted to DevGrill tokens.\n`;
    const content = mapStyleHooks(replaceIconPlaceholders(mapClasses(rewriteImports(file.content))));
    if (content.includes("lucide-react")) deps.add("lucide-react");
    writeFileSync(join(OUT, fileName), header + content, "utf8");
    console.log(`fetched ${name} → src/components/ui/${fileName}`);
  }
}
console.log(`dependencies: ${[...deps].sort().join(" ") || "(none)"}`);
