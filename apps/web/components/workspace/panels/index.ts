import { Code2, Database, Gauge, GitBranch, ScrollText, Zap } from "lucide-react";
import type { ReactNode } from "react";
import type { Tool } from "@devgrill/ui/components/devgrill/tool-rail";
import { CachePanel } from "./cache";
import { CodePanel } from "./code";
import { DatabasePanel } from "./database";
import { DeploysPanel } from "./deploys";
import { LogsPanel } from "./logs";
import { OverviewPanel } from "./overview";

/** The tool rail, in order (number keys pick from it): live incidents and case files share it. */
export const TOOLS: (Tool & { key: string })[] = [
  { id: "overview", key: "overview", label: "Overview", icon: Gauge },
  { id: "logs", key: "logs", label: "Logs", icon: ScrollText },
  { id: "database", key: "database", label: "Database", icon: Database },
  { id: "cache", key: "cache", label: "Cache", icon: Zap },
  { id: "code", key: "code", label: "Code", icon: Code2 },
  { id: "deploys", key: "deploys", label: "Deploys", icon: GitBranch },
];

export const PANELS: Record<string, () => ReactNode> = {
  overview: OverviewPanel,
  logs: LogsPanel,
  database: DatabasePanel,
  cache: CachePanel,
  code: CodePanel,
  deploys: DeploysPanel,
};
