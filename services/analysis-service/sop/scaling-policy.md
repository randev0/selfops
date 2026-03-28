# Scaling Policy

## Maximum Replica Limits
| Service Tier     | Min Replicas | Max Replicas | Notes                       |
|------------------|-------------|-------------|----------------------------|
| API (stateless)  | 1           | 4           | HPA recommended above 3    |
| Worker           | 1           | 2           | Stateful jobs — be careful  |
| Frontend         | 1           | 3           | Stateless, safe to scale    |
| Demo app         | 1           | 4           | Testing only                |

Never scale a deployment beyond its maximum without approval from the platform team.

## When to Scale Up
Scale up replicas when:
- CPU usage exceeds 70% for more than 3 minutes
- Request latency p99 exceeds 500ms
- Pod is in `Pending` state due to resource pressure

## When NOT to Scale Up
- If OOM is caused by a memory leak, scaling only delays the crash — fix the root cause.
- If the issue is database connection exhaustion, adding replicas worsens it.
- If current replicas are already at maximum.

## Scale Up Increment
Always scale by **+1 replica at a time**. Do not jump from 1 to 4 replicas in one step.

## Recommendation Template
"According to scaling-policy.md, scale_up is appropriate when CPU > 70% for 3+ minutes. Increment by 1 replica, max 4. If already at max, escalate."
