# Pod Restart Policy

## When to Restart
A pod restart (`rollout restart`) is appropriate when:
- The pod has restarted more than 3 times in 5 minutes (CrashLoopBackOff)
- Memory usage exceeds 90% of the limit for more than 2 minutes
- The pod is stuck in `Pending` state for more than 5 minutes and is not schedulable

## Preferred Restart Method
Always use **rolling restart** (`kubectl rollout restart deployment/<name>`) rather than deleting individual pods.
- Rolling restart maintains availability by replacing pods one at a time.
- Direct pod deletion can cause a brief outage if replicas = 1.

## Escalation Criteria
Escalate to on-call engineer if:
- The same pod restarts more than 5 times in 30 minutes after a restart action
- The crash is occurring on a stateful workload (databases, message brokers)
- The incident is in the `data` or `security` namespace

## Automation Safety
Automated restarts are **only** permitted for:
- Stateless deployments in the `platform` namespace
- Pods with `safe_for_auto: true` in the remediation policy
- During off-peak hours (17:00–08:00 UTC)

## Recommendation Template
"According to pod-restart-policy.md, a rolling restart is the preferred action for crash-looping pods. Use rollout_restart action, not direct pod deletion."
