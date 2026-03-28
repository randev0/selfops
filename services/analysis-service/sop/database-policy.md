# Database Operations Policy

## Scope
Applies to all PostgreSQL instances in the `platform` and `data` namespaces.

## Peak Hours Definition
**Peak hours: 08:00–17:00 UTC, Monday–Friday.**
Do not perform destructive or disruptive operations during peak hours without prior approval from the on-call DBA.

## Prohibited Actions During Peak Hours
- Restarting the primary database pod
- Running schema migrations that acquire table locks
- Dropping or truncating tables
- Changing connection pool limits downward

## Allowed Mitigations During Peak Hours
- Scale up read-replica pods (non-disruptive)
- Increase `max_connections` via ConfigMap (requires pod restart — defer to off-peak)
- Add or adjust connection pool size in the application layer (no pod restart needed)

## Preferred Remediation for Database OOM / High Memory
1. First: check for runaway queries with `pg_stat_activity` — kill them if safe.
2. Second: scale the read-replica to offload SELECT traffic.
3. Third: if restart is unavoidable, schedule during off-peak hours and notify stakeholders.

## Recommendation Template
"According to database-policy.md, we must not restart the DB pod during peak hours (08:00–17:00 UTC). Recommended action: scale read-replica or schedule restart for off-peak."
