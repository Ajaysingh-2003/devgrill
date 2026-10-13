import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { parseEnv } from "node:util";
import type { NextConfig } from "next";

// One .env for the whole repo (docs/PLAN.md §6). Next only reads apps/web/.env*, so load the
// root file here. Variables already set (CI, `just`, the shell) win over the file.
const rootEnv = join(import.meta.dirname, "..", "..", ".env");
if (existsSync(rootEnv)) {
  for (const [key, value] of Object.entries(parseEnv(readFileSync(rootEnv, "utf8")))) {
    if (process.env[key] === undefined && value !== undefined) process.env[key] = value;
  }
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // pg is a Node library: keep it out of the server bundle.
  serverExternalPackages: ["pg"],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
