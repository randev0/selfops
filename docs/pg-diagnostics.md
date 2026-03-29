# PostgreSQL Diagnostics Adapter

## Overview

The PostgreSQL diagnostics adapter performs **read-only** introspection of a
running PostgreSQL instance using `pg_stat_activity` and related system views.
It runs automatically as part of `enrich_incident` and stores the result as
`IncidentEvidence(evidence_type="database")`.

The snapshot captures connection counts, active queries, blocked queries,
long-idle connections, and wait events at the moment of incident detection.
If the target database is unreachable, enrichment continues normally — the
adapter fails silently and returns `available=false`.

---

## Required Database Permissions

The connecting user needs no superuser privileges.  The minimum required grant:

```sql
-- Create a dedicated read-only monitoring user
CREATE USER selfops_monitor WITH PASSWORD 'strong-password';

-- Grant access to the diagnostic views
GRANT pg_monitor TO selfops_monitor;
```

`pg_monitor` is a built-in PostgreSQL role (≥ 10) that grants read access to
`pg_stat_activity`, `pg_stat_database`, `pg_settings`, and related views
without exposing query text of other superusers.

If `pg_monitor` is not available (PG < 10):

```sql
GRANT SELECT ON pg_stat_activity TO selfops_monitor;
GRANT SELECT ON pg_stat_database TO selfops_monitor;
GRANT SELECT ON pg_settings      TO selfops_monitor;
```

---

## Configuration

All settings are read from environment variables (or the `.env` file).

| Environment variable | Default | Description |
|---|---|---:|
| `PG_DIAGNOSTICS_DSN` | `""` | asyncpg-format DSN (`postgresql://user:pw@host:5432/db`). Falls back to `DATABASE_URL` with `+asyncpg` prefix stripped. |
| `PG_DIAGNOSTICS_ENABLED` | `true` | Set to `false` to disable the adapter entirely. |
| `PG_DIAGNOSTICS_QUERY_TIMEOUT_SECONDS` | `10` | Per-statement timeout in seconds (clamped 1–60). |
| `PG_DIAGNOSTICS_MAX_ROWS` | `50` | Maximum rows returned from `pg_stat_activity` (clamped 1–500). |
| `PG_DIAGNOSTICS_MAX_QUERY_LENGTH` | `500` | Maximum characters of query text stored (clamped 50–2000). |
| `PG_DIAGNOSTICS_LONG_IDLE_THRESHOLD_SECONDS` | `300` | Connections idle longer than this appear in `long_idle_connections`. |

### Minimal setup (same database as SelfOps app)

No config needed.  The adapter falls back to `DATABASE_URL` automatically:

```
DATABASE_URL=postgresql+asyncpg://selfops:password@postgres:5432/selfops
```

### Separate monitoring user

```
PG_DIAGNOSTICS_DSN=postgresql://selfops_monitor:strong-password@postgres:5432/selfops
```

### Kubernetes secret

```bash
kubectl create secret generic selfops-pg-monitor \
  --from-literal=pg-diagnostics-dsn="$PG_DIAGNOSTICS_DSN" \
  -n platform --dry-run=client -o yaml | kubectl apply -f -
```

Reference in the worker deployment:

```yaml
env:
  - name: PG_DIAGNOSTICS_DSN
    valueFrom:
      secretKeyRef:
        name: selfops-pg-monitor
        key: pg-diagnostics-dsn
```

---

## Safety Guarantees

1. **Read-only session** — The adapter immediately executes
   `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` after connecting.
   Any accidental write statement will be rejected by the server before it runs.

2. **Statement timeout** — `SET statement_timeout = '<N>ms'` is applied per
   session.  Diagnostic queries that exceed the timeout are cancelled by the
   server; they do not block the worker.

3. **Parameterised queries** — All variable inputs (max rows, query length
   limit) are passed as bind parameters.  There is no string interpolation in
   SQL.

4. **No writes are possible** — The adapter package contains no INSERT, UPDATE,
   DELETE, or DDL statements.

5. **Isolated connection** — The adapter opens a fresh `asyncpg` connection
   separate from the SQLAlchemy pool used for storing evidence.  Diagnostic
   activity does not appear in the application's own `pg_stat_activity` rows.

---

## Correlation Rules

### Connection Saturation

```
connection_saturation_pct = (total_connections / max_connections) × 100
```

`max_connections` is read from `pg_settings`.  Saturation is `null` when
fewer than one connection is observed.

### Long-Idle Detection

A connection is flagged as long-idle when:

```
state = 'idle'  AND  state_duration_seconds ≥ pg_diagnostics_long_idle_threshold_seconds
```

`state_duration_seconds` is `EXTRACT(EPOCH FROM (now() - state_change))`.

### Blocked Query Detection

A connection is flagged as blocked when `pg_blocking_pids(pid)` returns a
non-empty array.  Each blocked query records the full list of blocking PIDs.

---

## Output Schema (`DatabaseDiagnostics`)

Stored in `IncidentEvidence.content` as JSON.

```json
{
  "available": true,
  "error_message": null,
  "captured_at": "2025-03-01T14:00:00+00:00",
  "database_name": "selfops",

  "total_connections": 12,
  "active_connections": 3,
  "idle_connections": 7,
  "idle_in_transaction_connections": 1,
  "waiting_connections": 1,
  "max_connections": 100,
  "connection_saturation_pct": 12.0,

  "long_idle_connections": [
    {
      "pid": 4201,
      "usename": "selfops",
      "application_name": "selfops-api",
      "state": "idle",
      "idle_duration_seconds": 612.3,
      "query_truncated": "SELECT 1"
    }
  ],
  "long_idle_threshold_seconds": 300,

  "blocked_queries": [
    {
      "pid": 5501,
      "usename": "selfops",
      "application_name": "selfops-worker",
      "query_truncated": "UPDATE incidents SET status = ...",
      "wait_event_type": "Lock",
      "wait_event": "relation",
      "blocked_duration_seconds": 8.1,
      "blocking_pids": [4201]
    }
  ],

  "top_queries": [
    {
      "pid": 4820,
      "usename": "selfops",
      "application_name": "selfops-api",
      "query_truncated": "SELECT * FROM incidents WHERE ...",
      "duration_seconds": 2.34,
      "wait_event_type": null,
      "wait_event": null
    }
  ],

  "connections_by_state": {
    "active": 3,
    "idle": 7,
    "idle in transaction": 1,
    "unknown": 1
  },

  "connections_by_application": {
    "selfops-api": 6,
    "selfops-worker": 4,
    "(unknown)": 2
  },

  "wait_events": [
    { "wait_event_type": "Lock", "wait_event": "relation", "count": 1 },
    { "wait_event_type": "IO",   "wait_event": "DataFileRead", "count": 3 }
  ],

  "db_stats": {
    "numbackends": 12,
    "xact_commit": 48291,
    "xact_rollback": 14,
    "blks_hit": 990241,
    "blks_read": 8821,
    "tup_returned": 1204811,
    "tup_fetched": 841023,
    "deadlocks": 0,
    "conflicts": 0
  }
}
```

When `available = false`, all numeric fields are `0`, all lists are empty,
and `error_message` explains why.

---

## Files Changed

| File | Change |
|---|---|
| `services/worker/pg_diagnostics/__init__.py` | New — package entry point, exports `fetch_diagnostics` |
| `services/worker/pg_diagnostics/models.py` | New — `LongIdleConnection`, `BlockedQuery`, `WaitEventSummary`, `ActiveQuery`, `DatabaseStats`, `DatabaseDiagnostics` |
| `services/worker/pg_diagnostics/config.py` | New — `PgDiagnosticsConfig` (pydantic-settings) |
| `services/worker/pg_diagnostics/adapter.py` | New — `PgDiagnosticsAdapter`, `_normalize()`, `fetch_diagnostics()` |
| `services/worker/worker.py` | Modified — `enrich_incident` calls `fetch_diagnostics`, stores as `database` evidence |
| `services/api/migrations/004_pg_diagnostics_evidence.sql` | New — expands evidence_type CHECK constraint to include `deploy_correlation` and `database` |
| `tests/worker/test_pg_diagnostics.py` | New — 44 unit tests |
| `docs/pg-diagnostics.md` | New — this file |

---

## Known Limitations

1. **Single-database snapshot** — The adapter queries the database it connects
   to.  Cross-database or cross-cluster monitoring is not supported.

2. **No historical data** — Each enrichment is a point-in-time snapshot.
   Transient spikes (e.g. a connection burst that resolved before enrichment
   ran) will not appear.

3. **Query text of superusers** — With `pg_monitor`, query text of other
   superuser sessions is not visible (shows `<insufficient privilege>`).
   This is intentional for security.

4. **No diff content** — Only query text truncated to `max_query_length` is
   stored.  Full query text, bind parameters, and execution plans are not
   captured.

5. **asyncpg only** — The production connection uses `asyncpg` directly.
   PgBouncer or other poolers in statement-pooling mode may suppress
   `pg_stat_activity` detail for pooled connections.

6. **No remediation** — The adapter is purely observational.  Detecting a
   blocked or long-idle connection does not trigger any kill/terminate action.
   Remediation is out of scope for this phase.

---

## Follow-up Tasks

- Surface `database` evidence in the AI analysis prompt so the LLM sees
  connection and blocking state.
- Add a `pg_locks` query to capture lock detail (granted/waiting by relation).
- Add threshold-based alerting: emit an `audit_log` warning when saturation
  exceeds a configurable percentage.
- Build a "Database Health" panel in the frontend using `DatabaseDiagnostics`.
- Add `GITHUB_REGRESSION_THRESHOLD_MINUTES` and pg diagnostics env vars to
  the Kubernetes worker deployment manifest.
