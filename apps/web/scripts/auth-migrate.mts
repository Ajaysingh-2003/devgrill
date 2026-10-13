/**
 * Create or update Better Auth's tables in the `auth` schema (`just db-migrate` runs this
 * after Alembic). Additive only: Better Auth refuses unsafe changes to populated tables.
 *
 * Usage: node scripts/auth-migrate.mts [--check | --reset]
 *   --check  exit 1 if changes are pending (CI)
 *   --reset  drop the auth schema first: deletes every account and session (`just db-reset`)
 */
import { getMigrations } from "better-auth/db/migration";
import { Client } from "pg";
import { AUTH_SCHEMA, authConfig, authDatabaseUrl } from "../lib/auth-config.mts";

const check = process.argv.includes("--check");
const reset = process.argv.includes("--reset");

const client = new Client({ connectionString: authDatabaseUrl() });
await client.connect();
if (reset) {
  await client.query(`DROP SCHEMA IF EXISTS ${AUTH_SCHEMA} CASCADE`);
  console.log("auth-migrate: dropped the auth schema");
}
await client.query(`CREATE SCHEMA IF NOT EXISTS ${AUTH_SCHEMA}`);
await client.end();

const config = authConfig();
const { toBeCreated, toBeAdded, toBeAddedIndexes, unsafeChanges, runMigrations } = await getMigrations(
  config,
  { throwOnUnsafe: false },
);
const pending = [
  ...toBeCreated.map((t) => `create table ${t.table}`),
  ...toBeAdded.map((t) => `add columns to ${t.table}: ${Object.keys(t.fields).join(", ")}`),
  ...toBeAddedIndexes.map((i) => `add index ${i.name}`),
];

if (unsafeChanges.length) {
  console.error(`auth-migrate: refusing unsafe changes:\n  ${unsafeChanges.join("\n  ")}`);
  process.exit(1);
}
if (!pending.length) {
  console.log("auth-migrate: auth schema is up to date");
} else if (check) {
  console.error(`auth-migrate: pending changes:\n  ${pending.join("\n  ")}`);
  process.exit(1);
} else {
  await runMigrations();
  console.log(`auth-migrate: applied ${pending.length} change(s):\n  ${pending.join("\n  ")}`);
}
const pool = config.database as { end?: () => Promise<void> };
await pool.end?.();
