// Rebuild the e2e database from scratch: create, migrate (Alembic + Better Auth), seed; and
// empty the e2e Valkey db (rate-limit buckets and idempotency keys from earlier runs).
// Run before Playwright (`pnpm e2e`). Refuses to touch any database not named *_e2e.
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import pg from "pg";
import { PG_URL, PYTHON, ROOT, STACK_ENV } from "./stack.mjs";

const url = new URL(PG_URL);
const database = url.pathname.slice(1);
if (!database.endsWith("_e2e")) throw new Error(`refusing to recreate ${database}`);

const admin = new pg.Client({
  connectionString: Object.assign(new URL(PG_URL), { pathname: "/postgres" }).toString(),
});
await admin.connect();
await admin.query(`DROP DATABASE IF EXISTS "${database}" WITH (FORCE)`);
await admin.query(`CREATE DATABASE "${database}"`);
await admin.end();

function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: ROOT, env: STACK_ENV, stdio: "inherit" });
  if (result.status !== 0) {
    console.error(`prepare-db: ${label} failed`);
    process.exit(result.status ?? 1);
  }
}

run("alembic", PYTHON, ["-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"]);
run("auth migrate", process.execPath, [join(ROOT, "apps/web/scripts/auth-migrate.mts")]);
run("seed", PYTHON, ["-m", "devgrill_content.cli", "seed"]);
run("valkey flush", PYTHON, [
  "-c",
  "import os, redis; redis.Redis.from_url(os.environ['VALKEY_URL']).flushdb()",
]);
console.log(`prepare-db: ${database} ready`);
