## What it is

Most regular expressions run in a blink. A few, given the wrong input, take exponential time. This is called catastrophic backtracking. Patterns with nested or overlapping repetition, like `(a+)+$` or `(\w+\s?)*$`, make the regex engine try a huge number of ways to match before it gives up. A 30-character input can take seconds, a 50-character one can take hours.

Python's built-in `re` module backtracks, so it is vulnerable. One request with a crafted or simply unlucky string, an email address, a user agent, a search query, pins a CPU core at 100% and never returns. When this is triggered on purpose it is called ReDoS, a regular expression denial of service.

## How it shows up in an incident

- One or more workers stuck at 100% CPU while the request count served drops.
- Requests time out, but only some of them, often on one endpoint that validates or parses text.
- Overall CPU spikes without a matching rise in traffic.
- It started with a deploy that added or changed a validation pattern, or a new kind of input arriving.
- Restarting helps until the same input arrives again.

## How to confirm it

Find the busy worker and see what it is running:

```sh
top -o %CPU
py-spy dump --pid 1234
```

A stack trace ending in `re` or `sre` matching functions inside validation or parsing code is the signature. Then look for the pattern in recent changes:

```sh
git log -p -3 | grep -n 're.compile\|re.match\|re.search'
```

Test the suspect pattern against a long, almost-matching string and time it:

```sh
python -c "import re,time; t=time.time(); re.match(r'(\w+\s?)*$', 'a'*28+'!'); print(time.time()-t)"
```

If adding a few characters to the input doubles the time, that is catastrophic backtracking.

## How to get it working again

- **Roll back** the deploy that introduced the pattern.
- **Restart the stuck workers** to free the CPU, knowing it will recur if the input comes back.
- **Limit input length** at the edge or in validation, which caps how bad the backtracking can get.
- **Block the offending requests** if one client is sending them.

## How to fix it properly

- Rewrite the pattern without nested or overlapping repetition. Prefer specific character classes over `.*`.
- Validate length before running any regex on user input.
- Use a linear-time regex engine for untrusted input, such as the `re2` bindings.
- Set request timeouts so one stuck request can't hold a worker forever.
- Test patterns against long almost-matching inputs, and use a linter that flags risky regexes.

## Common traps

- **Scaling up workers**, which gives the attacker more cores to pin.
- **Assuming a regex that passed unit tests is safe**: the tests rarely include worst-case input.
- **Writing your own email or URL regex** instead of using a tested library.
- **Running regexes on unbounded input** like whole request bodies or log lines.
