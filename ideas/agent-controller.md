# Agent Controller: Autonomous GitHub Issue Execution

## Executive Summary

A lightweight controller service that polls GitHub Issues for work and spawns Claude Code sessions to execute them autonomously. Combined with the `/gh-issue` skill, this enables fully automated task execution driven by GitHub Issues.

**Architecture:**
```
GitHub Issues (work queue)
        │
        ▼
┌─────────────────────┐
│ Agent Controller    │  ← Polls for ready parent issues
│ (charts/claude/)    │  ← Spawns Claude terminals
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Claude Code Session │  ← Uses /gh-issue skill
│ (tmux terminal)     │  ← Acquires lock, works children
└─────────────────────┘
        │
        ▼
PRs merged, issues closed
```

---

## Design Goals

1. **Simple**: Shell script or minimal Go/Python - no complex orchestration
2. **Resilient**: Handles failures gracefully, relies on lock TTL for recovery
3. **Observable**: Logs to stdout for SigNoz, metrics for monitoring
4. **GitOps-native**: Controller config lives in Helm values

---

## Architecture

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Controller script | `charts/claude/src/controller.sh` | Polls issues, spawns sessions |
| Controller deployment | `charts/claude/templates/controller.yaml` | K8s deployment |
| gh-issue-create skill | `.claude/skills/gh-issue-create/` | Bootstrap: design doc → issues |
| gh-issue skill | `.claude/skills/gh-issue/` | Execute: work issues → PRs |

### Issue States

```
┌──────────────┐     Controller picks up     ┌──────────────┐
│ agent-ready  │ ──────────────────────────► │ lock:xxx:ts  │
│ (no lock)    │                             │ (working)    │
└──────────────┘                             └──────────────┘
                                                    │
                    ┌───────────────────────────────┴──────────┐
                    ▼                                          ▼
            ┌──────────────┐                          ┌──────────────┐
            │ CLOSED       │                          │ needs-attn   │
            │ (completed)  │                          │ (failed)     │
            └──────────────┘                          └──────────────┘
```

### Lock Label Format

```
lock:<agent-id>:<unix-timestamp>
```

Example: `lock:claude-abc123:1706012345`

- **agent-id**: Unique identifier for the Claude session (e.g., pod name or UUID)
- **timestamp**: Unix epoch when lock was acquired
- **TTL**: 30 minutes (configurable)

---

## Controller Implementation

### Option A: Shell Script (Recommended for Simplicity)

**`charts/claude/src/controller.sh`:**
```bash
#!/bin/bash
set -euo pipefail

# Configuration
POLL_INTERVAL="${POLL_INTERVAL:-60}"       # Seconds between polls
LOCK_TTL="${LOCK_TTL:-1800}"               # Lock timeout in seconds (30 min)
REPO="${GITHUB_REPOSITORY:-jomcgi/homelab}"
LABEL_READY="${LABEL_READY:-agent-ready}"
MAX_CONCURRENT="${MAX_CONCURRENT:-1}"      # Max parallel sessions

log() {
    echo "[$(date -Iseconds)] $*"
}

# Check if issue has stale or no lock
is_available() {
    local issue_number=$1
    local lock_label

    lock_label=$(gh issue view "$issue_number" -R "$REPO" \
        --json labels -q '.labels[].name | select(startswith("lock:"))' || echo "")

    if [ -z "$lock_label" ]; then
        # No lock
        return 0
    fi

    # Parse timestamp from lock:agent:timestamp
    local lock_time
    lock_time=$(echo "$lock_label" | cut -d: -f3)
    local now
    now=$(date +%s)
    local age=$((now - lock_time))

    if [ "$age" -gt "$LOCK_TTL" ]; then
        log "Issue #$issue_number has stale lock (age: ${age}s), removing"
        gh issue edit "$issue_number" -R "$REPO" --remove-label "$lock_label"
        return 0
    fi

    # Lock is still valid
    return 1
}

# Count active Claude sessions
count_active_sessions() {
    tmux list-sessions -F '#{session_name}' 2>/dev/null | grep -c '^claude-issue-' || echo 0
}

# Spawn Claude session for issue
spawn_session() {
    local issue_number=$1
    local session_name="claude-issue-${issue_number}"

    log "Spawning session $session_name for issue #$issue_number"

    # Create tmux session running Claude with the gh-issue skill
    tmux new-session -d -s "$session_name" \
        "claude --skill gh-issue $issue_number; echo 'Session complete. Press enter to close.'; read"

    log "Session $session_name started"
}

# Main loop
main() {
    log "Agent Controller starting"
    log "Config: POLL_INTERVAL=${POLL_INTERVAL}s, LOCK_TTL=${LOCK_TTL}s, MAX_CONCURRENT=${MAX_CONCURRENT}"

    while true; do
        # Check concurrent session limit
        active=$(count_active_sessions)
        if [ "$active" -ge "$MAX_CONCURRENT" ]; then
            log "At capacity ($active/$MAX_CONCURRENT sessions), waiting"
            sleep "$POLL_INTERVAL"
            continue
        fi

        # Find ready issues
        log "Polling for issues with label: $LABEL_READY"
        issues=$(gh issue list -R "$REPO" \
            --label "$LABEL_READY" \
            --state open \
            --json number \
            -q '.[].number' || echo "")

        if [ -z "$issues" ]; then
            log "No ready issues found"
            sleep "$POLL_INTERVAL"
            continue
        fi

        # Try to claim an issue
        for issue in $issues; do
            if is_available "$issue"; then
                spawn_session "$issue"
                break  # Only spawn one per poll cycle
            else
                log "Issue #$issue is locked, skipping"
            fi
        done

        sleep "$POLL_INTERVAL"
    done
}

main "$@"
```

### Option B: Go Implementation (If More Control Needed)

A Go implementation would provide:
- Better error handling
- Structured logging for SigNoz
- Prometheus metrics endpoint
- More robust subprocess management

Only pursue this if the shell script proves insufficient.

---

## Kubernetes Deployment

### Deployment Manifest

**`charts/claude/templates/controller.yaml`:**
```yaml
{{- if .Values.controller.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "claude.fullname" . }}-controller
  labels:
    {{- include "claude.labels" . | nindent 4 }}
    app.kubernetes.io/component: controller
spec:
  replicas: 1  # Only one controller instance
  selector:
    matchLabels:
      {{- include "claude.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: controller
  template:
    metadata:
      labels:
        {{- include "claude.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: controller
    spec:
      serviceAccountName: {{ include "claude.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: controller
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          command: ["/app/controller.sh"]
          env:
            - name: POLL_INTERVAL
              value: "{{ .Values.controller.pollInterval }}"
            - name: LOCK_TTL
              value: "{{ .Values.controller.lockTTL }}"
            - name: MAX_CONCURRENT
              value: "{{ .Values.controller.maxConcurrent }}"
            - name: GITHUB_REPOSITORY
              value: "{{ .Values.controller.repository }}"
            - name: LABEL_READY
              value: "{{ .Values.controller.readyLabel }}"
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.controller.githubTokenSecret }}
                  key: token
          resources:
            {{- toYaml .Values.controller.resources | nindent 12 }}
          volumeMounts:
            - name: homelab-repo
              mountPath: /home/claude/repos/homelab
      volumes:
        - name: homelab-repo
          persistentVolumeClaim:
            claimName: {{ include "claude.fullname" . }}-repo
{{- end }}
```

### Values Configuration

**`charts/claude/values.yaml`** (additions):
```yaml
controller:
  enabled: false  # Enable when ready
  pollInterval: "60"      # Seconds
  lockTTL: "1800"         # 30 minutes
  maxConcurrent: "1"      # Max parallel sessions
  repository: "jomcgi/homelab"
  readyLabel: "agent-ready"
  githubTokenSecret: "github-token"
  resources:
    limits:
      cpu: 100m
      memory: 256Mi
    requests:
      cpu: 50m
      memory: 128Mi
```

---

## Claude Session Invocation

The controller spawns Claude with a specific command pattern:

```bash
claude --skill gh-issue <issue-number>
```

This:
1. Starts Claude Code CLI
2. Loads the `/gh-issue` skill instructions
3. Passes the issue number as argument
4. Claude reads the skill, acquires lock, executes workflow

### Alternative: Direct Prompt

If `--skill` flag isn't available, use a prompt file:

```bash
claude --prompt-file /app/prompts/gh-issue.md --context "Parent issue: $ISSUE_NUMBER"
```

**`charts/claude/src/prompts/gh-issue.md`:**
```markdown
You are working on a GitHub issue task. Follow the /gh-issue skill workflow:

1. Acquire lock on parent issue (provided in context)
2. Read the parent issue and any linked design docs
3. List open child issues
4. Pick the next logical child to work on
5. Create a worktree, make changes, submit PR
6. Wait for CI, merge if green
7. Close the child issue
8. Check if all children are done; if so, close parent
9. Release lock

Use the gh CLI for all GitHub operations.
Start by reading the parent issue to understand the task context.
```

---

## Observability

### Logging

Controller logs to stdout in structured format:
```
[2024-01-23T10:15:30+00:00] Agent Controller starting
[2024-01-23T10:15:30+00:00] Config: POLL_INTERVAL=60s, LOCK_TTL=1800s, MAX_CONCURRENT=1
[2024-01-23T10:15:30+00:00] Polling for issues with label: agent-ready
[2024-01-23T10:15:31+00:00] Found 2 ready issues: #42, #45
[2024-01-23T10:15:31+00:00] Issue #42 is available, spawning session
[2024-01-23T10:15:32+00:00] Session claude-issue-42 started
```

SigNoz ingests these via OTEL collector (auto-injected by Kyverno).

### Metrics (Future Enhancement)

If Go implementation is pursued:
```go
var (
    issuesPolled = prometheus.NewCounter(...)
    sessionsSpawned = prometheus.NewCounter(...)
    sessionDuration = prometheus.NewHistogram(...)
    activeSessionsGauge = prometheus.NewGauge(...)
)
```

---

## Error Handling

### Scenario: Claude Session Crashes

1. Lock remains on issue (has timestamp)
2. Controller polls, sees lock age > TTL
3. Controller removes stale lock
4. Next poll cycle, controller spawns new session
5. New session picks up where old one left off (or starts fresh on child)

### Scenario: CI Fails

1. Claude session detects CI failure
2. Adds `needs-attention` label to child issue
3. Releases lock on parent
4. Controller ignores issues with `needs-attention` children
5. Human investigates, fixes, removes label
6. Controller picks up on next poll

### Scenario: GitHub API Unavailable

1. `gh issue list` fails
2. Controller logs error, sleeps, retries
3. No special handling needed - transient failures self-heal

---

## Security Considerations

1. **GitHub Token**: Stored in Kubernetes secret, mounted as env var
2. **Limited Scope**: Token only needs `repo` scope for issues/PRs
3. **No Privilege Escalation**: Controller runs as non-root
4. **Read-Only Filesystem**: Except for tmux sockets and repo volume

---

## Testing Strategy

### Manual Testing

```bash
# 1. Create test parent issue
gh issue create --title "Test: Agent Controller" \
    --body "Design doc: ideas/agent-controller.md" \
    --label "agent-ready"

# 2. Add child issues
gh issue create --title "Test child 1" --parent <parent-number>
gh issue create --title "Test child 2" --parent <parent-number>

# 3. Run controller locally
GITHUB_TOKEN=xxx ./charts/claude/src/controller.sh

# 4. Watch session
tmux attach -t claude-issue-<number>
```

### Integration Testing

1. Deploy controller to cluster
2. Create test issue via CI
3. Assert PR is created within timeout
4. Assert issue is closed after merge

---

## Implementation Phases

### Phase 1: Skill Validation
- [x] Create `/gh-issue` skill
- [ ] Test skill manually with a real issue
- [ ] Verify lock acquire/release works

### Phase 2: Controller Script
- [ ] Implement `controller.sh`
- [ ] Test locally with mock issues
- [ ] Verify session spawning works

### Phase 3: Kubernetes Deployment
- [ ] Add controller deployment to claude chart
- [ ] Add values configuration
- [ ] Deploy to cluster
- [ ] Verify end-to-end flow

### Phase 4: Hardening
- [ ] Add structured logging
- [ ] Add retry logic for transient failures
- [ ] Add metrics (optional)
- [ ] Document operational procedures

---

## Controller Prompts

The controller uses two skills for different phases:

### Phase 1: Bootstrap (Create Issues from Design Doc)

```bash
claude "/gh-issue-create ideas/agent-controller.md"
```

This reads the design doc and creates:
- Parent issue with context/goal
- Child issues for each discrete task
- Labels parent as `agent-ready`

### Phase 2: Execute (Work the Issues)

```bash
claude "/gh-issue 42"
```

Where `42` is the parent issue number. This:
- Acquires lock on parent
- Reads context (parent + design doc)
- Picks and works child issues
- Submits PRs, merges on CI pass
- Closes issues on completion

### Full Autonomous Flow

```bash
# Human or scheduled job bootstraps new work
claude "/gh-issue-create ideas/new-feature.md"

# Controller polls and finds agent-ready issue, spawns:
claude "/gh-issue <parent-number>"
```

### Controller Spawn Command

The controller script spawns sessions with:

```bash
tmux new-session -d -s "claude-issue-${ISSUE}" \
    "claude '/gh-issue $ISSUE'"
```

---

## Open Questions

1. **Session Management**: Should we use tmux, or spawn separate pod per session?
   - tmux is simpler, works with existing claude deployment
   - Separate pods would provide better isolation but more complexity

2. **Concurrency**: How many parallel sessions should we support?
   - Start with 1, increase based on resource availability
   - Consider API rate limits

3. **Retry Logic**: How many times should we retry a failed child issue?
   - Current design: mark as `needs-attention`, human intervenes
   - Could add `retry-count:N` labels for automatic retry

---

## References

- `/gh-issue` skill: `.claude/skills/gh-issue/SKILL.md`
- Worktree workflow: `.claude/skills/worktree/SKILL.md`
- PR workflow: `.claude/skills/gh-pr/SKILL.md`
- Claude chart: `charts/claude/`
