## What it is

Configuration is everything a service reads at startup or runtime that isn't code: database addresses, cache settings, timeouts, pool sizes, limits, credentials, feature switches. A bad config change is one of the most common causes of outages, because config often skips the review, testing and gradual rollout that code gets. A single wrong value, a zero, a typo in a hostname, a unit mistake (seconds versus milliseconds), can break a service as surely as a code bug.

Config changes also hide well. The code didn't change, so "nothing was deployed" can feel true. And the effect may be indirect: a cache that stops caching, a pool that's too small, a timeout that's far too long.

## How it shows up in an incident

- Metrics shift right after a config change or a deploy that shipped new config, even with no code change.
- A behaviour change rather than a crash: caching stops, traffic goes to the wrong endpoint, limits are hit early.
- Only some instances are affected, if the change rolled out partially or one environment differs.
- Startup errors such as "invalid value" or "connection refused" when the service restarts with the new config.

## How to confirm it

Find what changed, and when. Line up the timing with the graphs:

```sh
git log --oneline -10 -- config/
git show HEAD -- config/
git diff HEAD~1 -- config/
```

Check what the running service actually loaded, which can differ from the file:

```sh
env | grep -E 'DATABASE|CACHE|TIMEOUT|POOL'
curl -s api:8000/config 2>/dev/null
```

Compare the values with a known-good environment or the previous release. Pay attention to units, zeros and hostnames.

## How to get it working again

- **Roll back the config change.** It's usually the fastest, safest fix, and it doesn't require understanding the cause first.
- **Restart instances** if the service only reads config at startup, so they pick up the restored values.
- **Check every environment and instance** got the rollback.

Editing config live on one server to fix it quickly leaves instances different from each other and from what's in version control. Fix it through the normal path, even under pressure, or record exactly what you changed.

## How to fix it properly

- Keep config in version control, and review changes like code.
- Validate config before it ships: types, ranges, required fields. Reject obviously bad values, like a pool size of zero or a negative timeout.
- Roll config out gradually, to a canary first, with automatic rollback on errors.
- Make the running config visible, through a status endpoint or startup logs, so responders can see what's loaded.
- Treat config deploys as deploys: mark them on dashboards.

## Common traps

- **"Nothing was deployed"**, while a config change shipped minutes earlier.
- **Hand-editing config on one server** and leaving the fleet inconsistent.
- **Unit confusion**, such as milliseconds read as seconds.
- **Defaults that hide errors**: a missing value silently falling back to something harmful.
