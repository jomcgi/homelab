# TTYD Session Manager - WebSocket Integration Plan

**Status**: ✅ MVP Implemented & Deployed
**Created**: 2025-11-06
**Completed**: 2025-11-07
**Goal**: Integrate UI mockup with backend by implementing WebSocket terminal connections and enhanced session data

---

## User Decisions

- ✅ **WebSocket**: Minimal implementation with port-forward fallback
- ✅ **Metadata**: Annotations only (no SQLite database)
- ✅ **Metrics**: metrics-server is running, integrate immediately
- ✅ **Artifacts**: Skip entirely for Phase 1

---

## Phase 1: WebSocket Terminal Connection (CRITICAL PATH)

**Estimated Time**: 1 day
**Priority**: CRITICAL

### Goal
Enable terminal access from UI via WebSocket, using kubectl port-forward as proxy mechanism.

### Tasks

- [x] Add `github.com/gorilla/websocket` to `go.mod`
- [x] Implement WebSocket upgrade handler in `main.go`
  - [x] Accept WebSocket connection from client
  - [x] Connect directly to pod IP via WebSocket (using pod IP instead of port-forward)
  - [x] Implement bidirectional proxy (client ↔ ttyd)
  - [x] Handle connection errors and cleanup
- [x] Create route: `GET /api/sessions/:id/terminal`
- [x] Update `SessionResponse` struct to include `terminal_url` field
- [x] Populate `terminal_url` with `/api/sessions/{id}/terminal`
- [ ] Test WebSocket connection with browser
- [ ] Test bidirectional I/O (type commands, see output)
- [ ] Test error handling (pod not found, connection refused)

### Implementation Notes

```go
// WebSocket proxy flow:
GET /api/sessions/:id/terminal (WebSocket upgrade)

Steps:
1. Upgrade HTTP → WebSocket (client connection)
2. Start kubectl port-forward to pod (ttyd-session-{id}:7681)
3. Connect to localhost:random_port via WebSocket
4. Bidirectional proxy between client ↔ ttyd
5. Clean up on disconnect
```

### Files Modified
- `charts/ttyd-session-manager/backend/main.go`
- `charts/ttyd-session-manager/backend/go.mod`

### Acceptance Criteria
- ✅ Can connect to terminal from UI
- ✅ Bidirectional I/O works (type commands, see output)
- ✅ Connection errors handled gracefully
- ✅ Port-forward cleans up on disconnect

---

## Phase 2: Enhanced Session Metadata (HIGH PRIORITY)

**Estimated Time**: 1 day
**Priority**: HIGH

### Goal
Return complete session data for UI rendering, including real-time metrics from K8s.

### Tasks

- [x] Update `SessionResponse` struct with new fields
  - [x] Add `CreatedAt` (time.Time)
  - [x] Add `LastActive` (time.Time)
  - [x] Add `Branch` (string from annotation)
  - [x] Add `AgeDays` (int, calculated)
  - [x] Add `MemoryUsage` (string from metrics)
  - [x] Add `CPUUsage` (string from metrics)
  - [x] Add `TerminalURL` (string)
  - [x] Update `Name` to use annotation instead of pod name
- [x] Add `k8s.io/metrics` dependency to `go.mod`
- [x] Implement metrics client setup
- [x] Create function to query pod metrics
  - [x] Get CPU usage from metrics API
  - [x] Get memory usage from metrics API
  - [x] Format as percentage or absolute values
  - [x] Handle metrics unavailable gracefully
- [x] Update session list handler (`GET /api/sessions`)
  - [x] Parse pod creation timestamp → `created_at`
  - [x] Parse pod update timestamp → `last_active`
  - [x] Read annotation `session-name` → `name`
  - [x] Read annotation `git-branch` → `branch`
  - [x] Calculate `age_days` from created_at
  - [x] Query metrics API for CPU/memory
  - [x] Populate `terminal_url`
- [x] Update session get handler (`GET /api/sessions/:id`)
  - [x] Apply same metadata enhancements
- [ ] Test with real pods
- [ ] Verify metrics show correctly in response

### Implementation Notes

```go
type SessionResponse struct {
    // Existing
    ID          string    `json:"id"`
    PodName     string    `json:"pod_name"`
    ImageTag    string    `json:"image_tag"`

    // Enhanced
    Name        string    `json:"name"`           // From annotation "session-name"
    CreatedAt   time.Time `json:"created_at"`     // Pod creation time
    LastActive  time.Time `json:"last_active"`    // Pod update time or now
    State       string    `json:"state"`          // active/suspended/terminated
    Branch      string    `json:"branch"`         // From annotation "git-branch"
    AgeDays     int       `json:"age_days"`       // Calculated
    MemoryUsage string    `json:"memory_usage"`   // From metrics API (e.g., "45%")
    CPUUsage    string    `json:"cpu_usage"`      // From metrics API (e.g., "12%")
    TerminalURL string    `json:"terminal_url"`   // WebSocket endpoint
}
```

### Files Modified
- `charts/ttyd-session-manager/backend/main.go`
- `charts/ttyd-session-manager/backend/go.mod`

### Acceptance Criteria
- ✅ UI displays user-friendly session names (not pod names)
- ✅ Git branch shown correctly from annotation
- ✅ Age calculated accurately (0 days = "today", 1 day = "1d", etc.)
- ✅ Real CPU/memory metrics displayed from K8s metrics API
- ✅ All session metadata fields populated
- ✅ Metrics gracefully handle unavailable data

---

## Phase 3: Suspend/Resume (MEDIUM PRIORITY - BLOCKED)

**Estimated Time**: 2 days
**Priority**: MEDIUM
**Status**: ⚠️ BLOCKED - Architecture decision needed

### Goal
Enable session lifecycle management without database.

### Architecture Decision Required

**Problem**: Without SQLite, how do we track suspended sessions?

**Options**:
- **A. ConfigMap**: Store suspended session metadata in ConfigMap
  - Pros: No database needed, K8s-native
  - Cons: Not ideal for this use case, ConfigMap size limits

- **B. Git branches**: Query GitHub API for branches matching `session-*` pattern
  - Pros: Git is source of truth
  - Cons: Requires GitHub API calls, rate limits

- **C. Skip suspend for MVP**: Only support active sessions and full delete
  - Pros: Simplest, fastest to implement
  - Cons: Can't pause sessions, only delete

- **D. Add minimal SQLite**: Just for suspended sessions
  - Pros: Proper state management
  - Cons: Adds complexity we wanted to avoid

**Recommendation**: Start with **Option C** (skip suspend for MVP), add later with SQLite.

### Tasks (if we implement suspend/resume)

- [ ] **DECISION**: Choose architecture approach above
- [ ] Implement suspend endpoint (`POST /api/sessions/:id/suspend`)
  - [ ] Exec into pod: `git add -A && git commit && git push`
  - [ ] Delete pod (PreStop hook also commits)
  - [ ] Store "suspended" state (method depends on decision)
- [ ] Implement resume endpoint (`POST /api/sessions/:id/resume`)
  - [ ] Check session is suspended
  - [ ] Recreate pod with git-clone from branch
  - [ ] Update state to "active"
  - [ ] Return session details
- [ ] Update list endpoint to show suspended sessions
- [ ] Test suspend → resume workflow
- [ ] Verify files restored correctly

### Files Modified
- `charts/ttyd-session-manager/backend/main.go`
- Possibly add ConfigMap or SQLite integration

### Acceptance Criteria (if implemented)
- ✅ Suspend commits all changes to git
- ✅ Resume restores exact file state
- ✅ Suspended sessions show in UI with state="suspended"
- ✅ Can resume after hours/days
- ✅ No data loss during suspend/resume cycle

---

## Phase 4: Fix Session Creation (QUICK WIN)

**Estimated Time**: 1 hour
**Priority**: HIGH (quick win, unblocks testing)

### Goal
Accept user-friendly session names and git branch in creation request.

### Tasks

- [x] Update `CreateSessionRequest` struct
  - [x] Change `name` field to `display_name`
  - [x] Add `git_branch` field (optional)
  - [x] Keep `image_tag` field (optional)
- [x] Update pod creation logic
  - [x] Store `display_name` in annotation `session-name`
  - [x] Store `git_branch` in annotation `git-branch`
  - [x] Use git_branch in initContainer git clone command
  - [x] Default git_branch to "session-{id}" if not provided
- [x] Update pod name generation
  - [x] Keep DNS-safe format: `ttyd-session-{8-char-uuid}`
  - [x] Display name stored in annotation, not pod name
- [ ] Test creating session with friendly name
- [ ] Test creating session with custom git branch
- [ ] Verify annotations stored correctly

### Implementation Notes

```go
type CreateSessionRequest struct {
    DisplayName string `json:"display_name" binding:"required"`  // User-friendly name
    GitBranch   string `json:"git_branch,omitempty"`            // Optional git branch
    ImageTag    string `json:"image_tag,omitempty"`             // Optional image tag
}

// Pod annotations:
Annotations: map[string]string{
    "session-name":   req.DisplayName,  // "Main Development"
    "git-branch":     gitBranch,        // "feature/api-refactor" or "main"
    "git-remote-url": gitRemoteURL,
    "image-tag":      imageTag,
}

// Pod name (DNS-safe):
Name: fmt.Sprintf("ttyd-session-%s", sessionID[:8])  // "ttyd-session-a1b2c3d4"
```

### Files Modified
- `charts/ttyd-session-manager/backend/main.go`

### Acceptance Criteria
- ✅ Can create session with friendly name like "Main Development"
- ✅ Can specify git branch (or defaults to session-{id})
- ✅ Pod name remains DNS-safe (ttyd-session-{id})
- ✅ Session list shows user-friendly names, not pod names

---

## Implementation Order

### Week 1 (MVP)

**Day 1** (Quick Wins)
1. ✅ **Phase 4**: Fix session creation (1 hour)
2. ✅ **Phase 2**: Enhanced metadata + metrics (rest of day 1)

**Day 2** (Core Feature)
3. ✅ **Phase 1**: WebSocket terminal (full day)

**Day 3** (Testing & Polish)
4. 🔄 Test end-to-end with UI mockup
5. 🔄 Bug fixes and error handling
6. 🔄 Documentation

### Week 2 (Optional)
- **Phase 3**: Suspend/resume (after architecture decision)
- Artifact support (if needed)
- Frontend implementation

**Total MVP Time**: 2-3 days for functional backend API

---

## Out of Scope (Phase 1 MVP)

The following features are explicitly **OUT OF SCOPE** for the initial implementation:

- ❌ **Artifact support** (list, preview, export) - Skipped per user decision
- ❌ **Claude context integration** (.claude/context.json parsing)
- ❌ **Session cloning** (create from existing branch)
- ❌ **Manual git commit** (POST /api/sessions/:id/commit)
- ❌ **Git history view** (GET /api/sessions/:id/git-log)
- ❌ **Frontend implementation** (focus on backend API first)
- ❌ **Session search/filtering**
- ❌ **Suspend all sessions** bulk action
- ❌ **Session templates** (predefined environments)
- ❌ **SQLite database** (annotations only for now)
- ❌ **Kubernetes Service per pod** (using port-forward instead)

These can be added in future phases after MVP is validated.

---

## Success Criteria (MVP)

The MVP is **successful** if we can demonstrate:

- ✅ **Create session** with user-friendly name ("Main Development")
- ✅ **List sessions** with complete metadata (name, branch, age, CPU, memory)
- ✅ **View session details** with all fields populated
- ✅ **Connect to terminal** via WebSocket in browser
- ✅ **Interactive terminal** with bidirectional I/O (type commands, see output)
- ✅ **Real metrics** from K8s metrics API shown in UI
- ✅ **Delete session** cleanly (pod + service removed, git committed)
- ✅ **Error handling** graceful (pod not found, connection errors)

---

## Technical Architecture

### Current Backend State

**Existing** (already implemented):
- ✅ Go backend with Gin framework
- ✅ Kubernetes client-go integration
- ✅ Pod lifecycle management (create, list, get, delete)
- ✅ Git integration (initContainer clones, PreStop commits)
- ✅ Envoy sidecar for tracing
- ✅ Session pod with ttyd worker
- ✅ RBAC permissions configured
- ✅ 1Password secret injection
- ✅ OpenTelemetry tracing

**Recently Implemented**:
- ✅ WebSocket proxy for terminal (direct pod IP connection)
- ✅ Complete session metadata in API responses
- ✅ K8s metrics API integration

**Still Missing**:
- ❌ Suspend/resume functionality (Phase 3 - deferred)
- ❌ Service per pod (using direct pod IP connection instead)

### Data Flow

```
UI (Browser)
    │
    ├─ HTTP ──> GET /api/sessions
    │           └─> Returns: [{id, name, branch, age, cpu, memory, ...}]
    │
    ├─ HTTP ──> POST /api/sessions {display_name, git_branch}
    │           └─> Creates: Pod + Annotations
    │
    ├─ WS ───> GET /api/sessions/:id/terminal (WebSocket)
    │           └─> Proxy: Client ↔ kubectl port-forward ↔ ttyd pod:7681
    │
    └─ HTTP ──> DELETE /api/sessions/:id
                └─> Deletes: Pod (PreStop commits to git)
```

### Pod Architecture

```
Session Pod: ttyd-session-{id}
├── Init Container: git-clone
│   └── Clone repo → checkout branch → initial commit
├── Container: envoy-sidecar (port 7681)
│   └── Proxy 7681 → ttyd:7682 with tracing
└── Container: ttyd-worker (port 7682)
    └── ttyd -p 7682 opencode
    └── PreStop: git add -A && git commit && git push

Volume: workspace (emptyDir)
└── /workspace/session/
    ├── .session/metadata.json
    ├── .claude/context.json
    ├── .claude/artifacts/
    └── work/
```

---

## Critical Decisions Log

### Decision 1: WebSocket Proxy Strategy
**Question**: Use port-forward or Kubernetes Services?
**Decision**: Port-forward for MVP (minimal implementation)
**Rationale**: Faster to implement, avoids Service creation overhead
**Trade-off**: Less robust than Services, but good enough for MVP

### Decision 2: Metadata Storage
**Question**: SQLite, annotations, or hybrid?
**Decision**: Annotations only
**Rationale**: Simplest approach, no database to manage
**Trade-off**: Can't track suspended sessions easily (need Phase 3 decision)

### Decision 3: Metrics Integration
**Question**: Integrate K8s metrics API?
**Decision**: Yes, metrics-server is running
**Rationale**: Provides real CPU/memory data, better UX
**Trade-off**: None, metrics-server already available

### Decision 4: Artifact Support
**Question**: Implement artifact preview?
**Decision**: Skip for MVP
**Rationale**: Focus on core terminal functionality first
**Trade-off**: Less feature-complete UI, but faster MVP

### Decision 5: Suspend/Resume (PENDING)
**Question**: How to track suspended sessions without database?
**Decision**: TBD (see Phase 3)
**Options**: ConfigMap, Git API, skip entirely, or add SQLite
**Recommendation**: Skip for MVP, add later with SQLite if needed

---

## Testing Plan

### Unit Tests (Optional for MVP)
- WebSocket proxy connection handling
- Metrics parsing and formatting
- Session metadata transformation
- Error handling edge cases

### Integration Tests (Required)
- [ ] Create session → pod appears with correct annotations
- [ ] List sessions → returns complete metadata
- [ ] Get session → returns single session details
- [ ] Connect to terminal → WebSocket establishes
- [ ] Terminal I/O → commands execute, output returns
- [ ] Delete session → pod deleted, git committed
- [ ] Metrics → CPU/memory values realistic
- [ ] Error cases → 404 for missing session, 500 for K8s errors

### Manual Testing Checklist
- [ ] Create session with name "Test Session"
- [ ] Verify session appears in list with all fields
- [ ] Connect to terminal in browser
- [ ] Type `ls -la` and see output
- [ ] Type `echo "test" > file.txt` and verify file created
- [ ] Check git branch created on GitHub
- [ ] Delete session
- [ ] Verify git commit appears in branch history
- [ ] Verify pod no longer exists

---

## Dependencies

### Go Modules (to add)
```go
github.com/gorilla/websocket      // WebSocket proxy
k8s.io/metrics                    // Metrics API client
```

### Kubernetes (required)
- ✅ K3s cluster running
- ✅ metrics-server deployed and working
- ✅ RBAC permissions for pod exec, metrics read
- ✅ GitHub token secret (ttyd-session-manager-github)

### External Services
- ✅ GitHub repository for session storage
- ✅ 1Password vault for secrets
- ✅ SigNoz for observability

---

## Rollback Plan

If MVP doesn't work or has critical issues:

1. **WebSocket broken**: Fallback to manual kubectl port-forward instructions
2. **Metrics unavailable**: Show "N/A" instead of actual values
3. **Annotations lost**: Recreate from git branch metadata
4. **Performance issues**: Reduce polling frequency, cache metrics

---

## Next Steps (After Plan Approval)

1. **Implement Phase 4** (session creation fix) - 1 hour
   - Quick win to unblock testing with friendly names

2. **Implement Phase 2** (enhanced metadata + metrics) - 1 day
   - Make UI functional with complete data

3. **Implement Phase 1** (WebSocket terminal) - 1 day
   - Core feature for terminal access

4. **Test end-to-end** with UI mockup
   - Verify all features work together

5. **Decide on Phase 3** (suspend/resume)
   - Evaluate if needed for MVP or defer

6. **Deploy to homelab** cluster
   - Update ArgoCD application
   - Test in production environment

**Estimated time to functional MVP: 2-3 days**

---

## Questions & Answers

**Q: Why not use Kubernetes Services for WebSocket?**
A: Port-forward is simpler for MVP. Services add complexity (create/delete lifecycle). We can upgrade later.

**Q: How do we handle concurrent terminal connections?**
A: One WebSocket per client. Multiple clients can connect to same session (ttyd supports this).

**Q: What if metrics-server fails?**
A: Gracefully return "N/A" or last known values. Non-critical for core functionality.

**Q: Can we add artifacts later?**
A: Yes! Artifact support is independent. Can add in Phase 5 after MVP validated.

**Q: Should we implement suspend if we skip database?**
A: No, defer suspend/resume until we add SQLite or choose ConfigMap approach.

---

## References

- **Design Doc**: `ideas/ttyd-session-manager/context.md`
- **UI Mockup**: `ideas/ttyd-session-manager/ui-mockup.jsx`
- **Backend Code**: `charts/ttyd-session-manager/backend/main.go`
- **Helm Chart**: `charts/ttyd-session-manager/`
- **Deployment**: `overlays/dev/ttyd-session-manager/`

---

**Last Updated**: 2025-11-07
**Status**: ✅ MVP Implemented & Deployed to Cluster

## Implementation Summary

**Completed Phases**:
- ✅ Phase 4: Session creation with display_name and git_branch
- ✅ Phase 2: Enhanced metadata with K8s metrics integration
- ✅ Phase 1: WebSocket terminal connections

**Deployment Status**:
- ✅ Code committed and pushed to main
- ✅ CI pipeline built and pushed images to ghcr.io
- ✅ ArgoCD synced and deployed to ttyd-sessions namespace
- ✅ Backend API running with all new features

**Next Steps**:
- Testing WebSocket connections from UI
- Implementing frontend components
- Phase 3 (suspend/resume) - deferred pending architecture decision
