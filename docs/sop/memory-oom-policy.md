# Memory OOM & Resource Limit Policy

## OOM Kill Response
When a container is OOM-killed (`reason: OOMKilled` in pod events):

1. **Immediate**: Check if the OOM is caused by a runaway request or memory leak in logs.
2. **Short-term**: Increase the memory limit by **1.5× the current limit** via GitOps PR.
3. **Long-term**: File a task to profile and fix the memory leak.

## Memory Limit Increase Guidelines
- Minimum bump: 1.5× current limit
- Maximum single bump: 3× current limit (larger increases require architecture review)
- New limit must not exceed 2Gi for application pods without platform team approval
- Database and cache pods have separate limits (see database-policy.md)

## Example
Current limit: `256Mi` → New limit: `384Mi` (1.5×)
Current limit: `512Mi` → New limit: `768Mi` (1.5×)

## Approved Memory Limits by Tier
| Tier         | Soft Cap | Hard Cap (requires approval) |
|--------------|----------|------------------------------|
| API          | 512Mi    | 1Gi                          |
| Worker       | 512Mi    | 1Gi                          |
| Analysis     | 768Mi    | 1.5Gi                        |
| Frontend     | 256Mi    | 512Mi                        |

## GitOps Requirement
All memory limit changes **must** be applied via a GitOps PR (GITOPS_PR strategy).
Do not apply memory changes directly with `kubectl edit` — changes must be tracked in git.

## Recommendation Template
"According to memory-oom-policy.md, OOM-killed containers should have their memory limit increased by 1.5× via a GITOPS_PR. Direct kubectl edits are not permitted for resource limit changes."
