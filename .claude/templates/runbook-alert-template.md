# Alert Runbook

## Alert Information

### Service Details

- **Service Name**: [Service name from alert]
- **Namespace**: [Kubernetes namespace]
- **Alert Name**: [Alert rule name]
- **Alert Type**: [Metric/Log/Trace-based]

### Severity

- [ ] Critical - Service down or data loss risk
- [ ] High - Major functionality degraded
- [ ] Medium - Partial degradation, workaround available
- [ ] Low - Minor issue, no immediate impact

### Alert Context

- **Triggered At**: [Timestamp]
- **Duration**: [How long has the alert been firing]
- **Affected Components**: [List pods, deployments, or services]

## Initial Triage

### Step 1: Check SigNoz Dashboard

```
1. Open SigNoz at https://signoz.mcgibbon.ie
2. Navigate to Services > [service-name]
3. Check the following:
   - [ ] Error rate trend
   - [ ] Latency percentiles (p50, p95, p99)
   - [ ] Request throughput
```

### Step 2: Review Logs in SigNoz

```
1. Go to Logs Explorer
2. Filter by: service.name = [service-name]
3. Time range: Last 30 minutes
4. Look for:
   - [ ] Error level logs
   - [ ] Exception stack traces
   - [ ] Connection failures
```

### Step 3: Check Traces

```
1. Go to Traces in SigNoz
2. Filter by service and error status
3. Examine:
   - [ ] Span duration anomalies
   - [ ] Error spans and their root cause
   - [ ] Downstream service failures
```

### Step 4: Kubernetes Status Check

```bash
# Check pod status
kubectl get pods -n [namespace] -l app=[service-name]

# Check recent events
kubectl get events -n [namespace] --sort-by='.lastTimestamp' | tail -20

# Check pod logs
kubectl logs -n [namespace] -l app=[service-name] --tail=100

# Check resource usage
kubectl top pods -n [namespace] -l app=[service-name]
```

## Common Root Causes

### Resource Issues

- [ ] OOMKilled - Pod exceeded memory limits
- [ ] CPU throttling - Pod hitting CPU limits
- [ ] Storage full - PVC capacity exhausted
- [ ] Node pressure - Node running low on resources

### Network Issues

- [ ] DNS resolution failures
- [ ] Network policy blocking traffic
- [ ] Linkerd sidecar issues
- [ ] Upstream service unavailable

### Application Issues

- [ ] Configuration error (bad values.yaml)
- [ ] Secrets/ConfigMaps missing or invalid
- [ ] Database connection failures
- [ ] External API dependency down

### Infrastructure Issues

- [ ] Node failure
- [ ] Storage backend issues (Longhorn)
- [ ] Certificate expiration
- [ ] ArgoCD sync failure

## Resolution Steps

### Immediate Mitigation

[Document steps to reduce impact while investigating]

1. [Step 1]
2. [Step 2]
3. [Step 3]

### Root Cause Fix

[Document the fix after identifying root cause]

**Note**: Remember this cluster is GitOps-managed. All fixes must be applied via Git commits, not kubectl commands.

1. **Change Required**: [Description]
   - File: `projects/[service]/deploy/values.yaml`
   - Modification: [What needs to be changed]

2. **Verification**:
   ```bash
   # After ArgoCD syncs (5-10 seconds), verify:
   kubectl get pods -n [namespace] -l app=[service-name]
   kubectl logs -n [namespace] -l app=[service-name] --tail=50
   ```

## Post-Incident Actions

### Immediate

- [ ] Verify alert has resolved in SigNoz
- [ ] Confirm service health via dashboard
- [ ] Notify affected users if applicable

### Follow-up

- [ ] Document timeline of events
- [ ] Identify prevention measures
- [ ] Create issue for permanent fix if workaround applied
- [ ] Update monitoring/alerting if gaps identified
- [ ] Schedule post-mortem if severity was Critical or High

## Escalation Path

| Level | Contact             | When to Escalate                 |
| ----- | ------------------- | -------------------------------- |
| L1    | [Primary on-call]   | Initial alert                    |
| L2    | [Secondary on-call] | After 30 min without resolution  |
| L3    | [Service owner]     | Infrastructure or complex issues |

## Related Resources

- **Service Documentation**: [Link to service docs]
- **ArgoCD Application**: [Link to ArgoCD app]
- **SigNoz Dashboard**: [Link to service dashboard]
- **Previous Incidents**: [Links to related incidents]
