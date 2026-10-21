# Phase 5 red team: can a broken fix pass verify?

Date: 2026-10-21 · Gate: "deleting or modifying anything inside the sandbox (as root) cannot make a broken fix pass (red-team checklist of 10 attempts, documented)" · Design: ADR 015.

## What the attacker has

Everything a player has, used in bad faith:
- **root** in the shell container (`tools`);
- **the API's code and config**, editable and deployable;
- **SQL as the app's database role** (`shopkart`), which owns the app's tables;
- **Redis and Toxiproxy**, reached over the sandbox network;
- **verify's timing**, known: a run takes 1–2 minutes and is announced.

What they don't have: a shell in any other container (the probe, Postgres, Redis, the exporters), the Docker API, or the platform's network. Phase 3's isolation gate covers that boundary.

## How attempts are checked

- **Cheats** are content: `approaches/9x-cheat-*.yaml`, with `cheat: true`. `devgrill-content test --approaches` applies each one to a broken sandbox in a real run, then runs verify, which must fail. CI runs them on every content change and nightly, one job per scenario.
- **The verifier's own refusals** are unit-tested with a fake driver (`packages/py-core/tests/test_verifier.py`).
- **The database's refusals** were checked against the built image (role and privilege checks below).

## The checklist

| # | Attempt | Where it runs | Result |
|---|---|---|---|
| 1 | **Forge the telemetry.** Patch the API so every product lookup reports a cache hit and no database queries are counted; fix nothing | Cheat `cheat-forge-metrics` (ttl-zero, big-sale-meltdown) | **Fails verify.** Probe targets use database work measured from Postgres's own statistics: 1.96 scans per request, target under 1.0. The app's metrics only feed the charts |
| 2 | **Shed the load.** Answer 503 for product pages, so nothing reaches the database | Cheat `cheat-shed-load` (all three) | **Fails verify.** The replay's error rate is 85%, and the correctness test sees 503s instead of products |
| 3 | **Hard-code the sale.** Serve the five hot products from a copy taken once; everything else as before | Cheat `cheat-static-hot` (ttl-zero) | **Fails verify.** The correctness test changes a hot product's price; the page keeps the old one |
| 4 | **Reset the statistics during verify.** `pg_stat_reset()` and `pg_stat_statements_reset()`, once and then every second in the background | Cheat `cheat-reset-stats` (ttl-zero) | **Refused by Postgres**: permission denied (the app role isn't a superuser). The unfixed system still fails (1.94 scans per request). A reset by anyone during a replay fails the probe (unit test) |
| 5 | **Stop verify emptying the cache.** Apply the real fix, then `ACL SETUSER default -flushall -flushdb`, so the cold-cache check can't flush | Cheat `cheat-block-flush` (big-sale-meltdown) | **Fails verify.** The cache answers the verifier's FLUSHALL with `NOPERM`; `redis-cli` exits 0 on that, so verify checks the answer and fails the cold-cache probe as tampered |
| 6 | **Remove the chaos.** Delete the verifier's Toxiproxy toxic while the chaos window runs | Unit test `test_a_removed_toxic_fails_the_chaos_probe` | **Fails the probe.** The toxic is checked at the end of the window, and removed afterwards either way. No shipped scenario uses a toxic yet (see "Known limits") |
| 7 | **Shadow the catalog.** Create a schema or objects that the verifier's `search_path` would read instead of `pg_catalog` | Built image: `CREATE SCHEMA verifier` as the app role | **Refused**: permission denied for database (no CREATE on it). The verifier also pins `search_path = pg_catalog, …` per session and names `pg_catalog` explicitly |
| 8 | **Replace the stats extension.** `DROP EXTENSION pg_stat_statements`, then a fake table with the same name | Built image, as the app role | **Refused**: must be owner of the extension. It lives in a `monitor` schema owned by the platform's superuser |
| 9 | **Take over the database.** Log in as `postgres` with a guessed password; or `ALTER ROLE verifier` to change how verify's queries run | Built image, from another container on the network | **Refused**: the superuser's password is random and discarded at build time (scram over the network). Altering the verifier's role needs CREATEROLE, which the app role lacks |
| 10 | **Fake a recovery.** Make the API's own latency metrics look healthy right after the chaos, without recovering | Verifier design; unit test `test_recovery_comes_from_k6s_own_results` | **Fails the probe.** Recovery is computed by `dg-recovery` from k6's per-request results in the probe container, not from the app's metrics |

Plus the known approaches that aren't cheats but must not pass:

| Approach | Declared | Result |
|---|---|---|
| big-sale-meltdown `read-plain-key`: reads the old key again; latency recovers | partial: fails `correctness`, `price-freshness` | **Exactly those two fail.** Price changes stay hidden |
| pool-party `bigger-pool`: `DB_POOL_MAX=50` | fails `steady-traffic` | **Fails `steady-traffic`** (p99 649 ms against 500). Under the replay the API used only ~27 connections, so the headroom probe isn't what catches it; the round trip is. The declaration was corrected after this run |

## Known limits

- **Bypassing Toxiproxy.** The app could connect to the datastores directly and dodge a toxic-based chaos probe. No shipped scenario uses one. The fix is a split network where only Toxiproxy reaches the datastores; it lands with the first toxic chaos probe (ADR 015, "Negative").
- **Mitigation time** is detected from the app's own metrics during play. A player who forges them could claim an early "mitigated". The score only credits mitigation once a verify run held the SLO under replay and chaos, measured from outside. A forged early mitigation still earns credit if a real fix follows. Phase 6's review of the trail can flag it.
- **The verifier's password** (`verifier`) is in the content repository. Logging in as that role gains nothing: it is read-only, and it can't change what the verifier's sessions read.
