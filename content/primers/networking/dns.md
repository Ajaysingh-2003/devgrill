## What it is

DNS turns names like `payments.internal` into IP addresses. Almost every network call starts with a DNS lookup, often cached for a while according to the record's time-to-live (TTL). Because it sits underneath everything, a DNS problem can look like many unrelated failures at once.

Common DNS incidents: a record changed to the wrong address, a record deleted, a resolver that is slow or overloaded, a long TTL that keeps an old address cached after a migration, or an application that resolves a name once at startup and never again, so it keeps calling a server that has moved.

## How it shows up in an incident

- Errors such as "Name or service not known", "could not resolve host", `NXDOMAIN` or `SERVFAIL`.
- Connection errors or timeouts to one dependency, while it looks healthy from elsewhere.
- Some instances work and others fail, depending on what they cached.
- Latency added to every new connection when the resolver is slow.
- Problems right after a migration, failover or infrastructure change.

## How to confirm it

Resolve the name from the affected machine, the way the application would:

```sh
getent hosts payments.internal
dig payments.internal +short
dig payments.internal +noall +answer
```

Compare with what a different resolver or a healthy machine sees, and check the TTL in the answer. Time the lookup itself to see whether the resolver is slow:

```sh
dig payments.internal | grep 'Query time'
```

Check whether the application cached an old address. Connections to an IP that no longer belongs to the service are the signature:

```sh
ss -tnp | grep python
```

## How to get it working again

- **Fix or restore the record** if it was changed or deleted. Changes take up to the old TTL to reach everyone.
- **Restart the application instances** that cached the old address, if the app resolves names only at startup.
- **Point at a known-good address** temporarily through config if DNS itself is down.
- **Roll back** the infrastructure change that moved or renamed the service.

Remember the TTL: if the old record had a one-hour TTL, some clients may keep the wrong answer for up to an hour after the fix.

## How to fix it properly

- Lower TTLs ahead of planned migrations, then raise them again afterwards.
- Make sure clients re-resolve names: connection pools should not hold one address forever.
- Run resolvers with redundancy, and cache locally to survive short resolver outages.
- Manage DNS records as code, with review, history and easy rollback.
- Monitor resolution success and time from where the applications run.

## Common traps

- **Assuming DNS can't be the problem** because the name worked yesterday.
- **Fixing the record and expecting instant recovery** while old answers are still cached.
- **Long TTLs during a migration**, which slow down both the change and any rollback.
- **Testing from your laptop** instead of from the machine that is failing.
