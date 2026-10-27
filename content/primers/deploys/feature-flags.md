## What it is

A feature flag lets you turn behaviour on or off without deploying new code. Teams use flags to ship code dark and enable it later, to roll a feature out to a small share of users first, to run experiments, and as kill switches for risky paths. During an incident, a well-placed flag is often the fastest way to stop the damage.

Flags also cause incidents. Turning one on can start a slow code path for everyone at once. A flag change rarely goes through review or appears on deploy dashboards. Old flags pile up, and combinations nobody tested get switched on. And a flag service outage can change behaviour across the whole system if defaults are wrong.

## How it shows up in an incident

- A sudden change in errors or latency with no code deploy: someone flipped a flag.
- Only some users or a percentage of traffic affected, matching a gradual rollout.
- Behaviour that differs between instances, if flag values are cached or loaded at different times.
- A spike in load on a dependency right when a new feature was enabled.

## How to confirm it

Check the flag change history, and line it up with the graphs. Most flag systems keep an audit log of who changed what and when.

```sh
grep -i flag deploy.log | tail -20
grep -i 'flag' api.log | tail -20
```

Look at which code paths a flag controls and whether the failing requests go through them:

```sh
git grep -n 'is_enabled\|flags.get' -- '*.py'
```

Compare behaviour with the flag on and off for one test request, if you can set it per request or per user.

## How to get it working again

- **Turn the flag back off.** If the incident started with a flag change, reverting it is usually the fastest fix.
- **Use a kill switch**: if a risky feature has a flag, switch it off while you investigate, even if you're not sure it's the cause.
- **Reduce the rollout percentage** instead of switching off entirely, if a small share of traffic is safe.

Check that the change reached every instance. Some services cache flag values for minutes.

## How to fix it properly

- Treat flag changes as production changes: audit log, owner, and a note of why.
- Show flag changes on dashboards next to deploys.
- Roll out gradually, starting with a small percentage, and watch error rates before increasing.
- Make defaults safe: if the flag service is down, a flag should fall back to the old, known-good behaviour.
- Remove flags once a feature is fully rolled out, so dead flags and untested combinations don't pile up.
- Load-test the "on" path before enabling it for everyone.

## Common traps

- **Not checking flag history** because "nothing was deployed".
- **Enabling a feature for 100% of traffic at once**, skipping the gradual rollout flags exist for.
- **Unsafe defaults**, so a flag service blip turns features on everywhere.
- **Leaving old flags forever**, until someone flips one nobody remembers.
