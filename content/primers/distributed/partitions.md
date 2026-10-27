## What it is

A network partition happens when some parts of a system can't talk to others, while each part keeps running. A data centre loses its link to another, a misconfigured firewall blocks one subnet, a switch fails, or a node is too overloaded to answer in time, which looks the same from outside. Both sides are alive, but each thinks the other is down.

Partitions force a choice. A system can stay available, letting both sides keep accepting writes and risking conflicting data, or stay consistent, refusing some requests until the partition heals. The most dangerous outcome is split brain: two nodes each believe they are the primary, both accept writes, and the data diverges.

## How it shows up in an incident

- Timeouts and connection errors between specific services or zones, while each looks healthy on its own.
- Failovers that trigger even though the primary is still running.
- Two nodes reporting themselves as leader or primary at the same time.
- Conflicting or missing data after the network recovers: writes accepted on both sides.
- Some users fine, others failing, depending on which side of the split they reach.

## How to confirm it

Test connectivity from each side to the other, not just from your laptop:

```sh
ping -c 3 db-primary
nc -vz db-primary 5432
curl -s -o /dev/null -w '%{http_code} %{time_total}\n' payments:8080/health
```

Check what each node believes about the cluster. For Postgres replication, check whether each node thinks it is the primary:

```sql
select pg_is_in_recovery();
```

Two nodes returning `false` is split brain. Look for failover or leader election events in logs from both sides around the same time.

## How to get it working again

- **Stop writes on one side** if two primaries exist: fence the old primary so it can't accept writes, before anything else.
- **Route all traffic to one side** that you trust as the source of truth.
- **Restore connectivity**, then let replicas resync from the chosen primary.
- **Reconcile writes** made on the losing side, from logs or by comparing data, before discarding them.

Bringing both sides back without fencing one can make the divergence worse. Decide which side wins first.

## How to fix it properly

- Use consensus-based leader election that needs a majority (a quorum), so a minority side can't elect its own leader.
- Fence old primaries automatically during failover, so a node that comes back can't keep writing.
- Use timeouts and health checks that tell "slow" from "gone" as well as possible, and don't fail over on one missed check.
- Decide per feature whether to prefer availability or consistency, and make that explicit in design.
- Practise partitions in staging with tools that drop traffic between services.

## Common traps

- **Failing over on a single missed health check**, which turns a brief network blip into split brain.
- **Assuming a node that can't be reached is down**, when it may still be serving other clients.
- **Healing the partition before fencing**, letting both primaries keep writing.
- **Only testing full outages**, never partial ones where some links still work.
