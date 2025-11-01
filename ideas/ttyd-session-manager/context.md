# TTYD Session Manager - Minimal POC Deployment Plan

## Overview

A session manager that wraps ttyd (terminal over HTTP) with persistent sessions, Claude context preservation, and artifact preview capabilities. **Sessions run as isolated Kubernetes pods with Git-based persistence for simplicity and reliability.**

### Why Git for Persistence?

**Traditional approach (PVCs):**
- Complex: Manage PVCs, backup policies, storage classes
- Opaque: Can't inspect session state without exec-ing into pod
- Fragile: PVC corruption = data loss
- Heavy: Storage overhead for every session

**Git-first approach:**
- Simple: `git clone` on start, `git commit && push` on exit
- Transparent: Browse any session on GitHub
- Durable: Git history = built-in versioning + backup
- Lightweight: Ephemeral pods, Git remote is source of truth
- Developer-friendly: Standard Git workflows apply

## Core Concept

Allow users to create, suspend, and resume terminal sessions while maintaining:
- Git branch context
- Claude conversation history
- Generated artifacts (React components, images, HTML)
- Resource usage tracking
- Pod-level isolation and sandboxing

## Minimum Viable Architecture

```
┌──────────────────┐
│  React Frontend  │ ← Session Manager UI
│  (Port 3000)     │
└────────┬─────────┘
         │
         ↓
┌──────────────────┐
│   API Server     │ ← Session management, K8s orchestration
│   (Go + Gin)     │    - Manages pod lifecycle
│   (Port 8080)    │    - Handles finalizers
└────────┬─────────┘
         │
         ├──→ SQLite ← Session metadata only
         │
         └──→ Kubernetes API
                  │
                  ↓
         ┌─────────────────────────────────────┐
         │  Session Pods (one per session)     │
         │  ┌───────────────────────────────┐  │
         │  │ Container: ttyd + git         │  │
         │  │ - Runs bash shell             │  │
         │  │ - Port 7681                   │  │
         │  │ - Ephemeral storage           │  │
         │  │ - Git repo cloned at startup  │  │
         │  │ - Finalizer commits on exit   │  │
         │  └───────────────────────────────┘  │
         │  Git remote = persistent storage    │
         └─────────────────────────────────────┘
                          │
                          ↓
                   ┌──────────────┐
                   │  Git Remote  │ ← Session state, artifacts, Claude context
                   │  (GitHub)    │    - One branch per session
                   └──────────────┘
```

## Why Kubernetes Pods + Git?

### Kubernetes Benefits
1. **Isolation**: Each session in its own sandbox
2. **Resource limits**: CPU/memory per session enforced by K8s
3. **Security**: securityContext, network policies
4. **Observability**: Native K8s metrics via kubectl
5. **Cleanup**: Delete pod = cleanup complete
6. **Fits homelab**: Leverage existing infrastructure

### Git as Persistence Layer
1. **Simplicity**: No PVC management, no artifact upload APIs
2. **Version history**: Full history of session evolution
3. **Free backup**: Git remote = automatic backup
4. **Inspection**: Browse session state on GitHub
5. **Recovery**: Clone any session, anywhere
6. **Lightweight**: Just commit files when pod exits
7. **Claude-friendly**: Natural place to store conversation context

### Session Lifecycle with Git
1. **Create**: Spawn pod → clone session repo → checkout branch
2. **Work**: User interacts with terminal, Claude creates artifacts
3. **Suspend**: Finalizer triggers → commit all changes → push → delete pod
4. **Resume**: Spawn pod → clone repo → restore state
5. **Delete**: Delete pod → delete Git branch (optional)

## Components Required

### 1. Frontend (React App)
**File**: `ttyd-session-manager.jsx` (already exists)

**Changes needed**:
- Replace mock data with API calls to backend
- Connect to ttyd via proxy/port-forward through API server
- Environment config for API endpoint

**Deployment**:
- Simple static bundle served by API server
- Or separate container in same namespace

### 2. Backend API Server (Go)
**Responsibilities**:
- Session CRUD operations
- Create/delete Kubernetes pods with finalizers
- Store session metadata in SQLite
- Proxy terminal connections to ttyd pods
- Handle finalizer webhooks (commit on pod deletion)
- Manage Git branches per session

**Endpoints**:
```
GET    /api/sessions                    - List all sessions
POST   /api/sessions                    - Create new session (spawns pod + git branch)
GET    /api/sessions/:id                - Get session details
DELETE /api/sessions/:id                - Delete session (triggers finalizer → commit → delete pod)
POST   /api/sessions/:id/suspend        - Commit changes, delete pod (keep branch)
POST   /api/sessions/:id/resume         - Recreate pod, clone from branch
GET    /api/sessions/:id/terminal       - WebSocket proxy to ttyd
GET    /api/sessions/:id/metrics        - Get pod resource usage
POST   /api/sessions/:id/commit         - Manual commit (optional)
GET    /api/sessions/:id/git-log        - View session history
```

**Dependencies**:
- `client-go` - Kubernetes API client
- `gin-gonic/gin` - HTTP framework
- `modernc.org/sqlite` - Embedded database
- `gorilla/websocket` - WebSocket proxy
- `go-git/go-git` - Git operations (optional, can just exec `git`)

**RBAC Requirements**:
```yaml
# ServiceAccount needs permissions to:
- pods (create, get, list, delete, watch, update/patch for finalizers)
- pods/exec (exec into pod to run git commands)
- services (create, delete)
```

### 3. Session Storage (SQLite)
**Schema**:
```sql
-- sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,              -- UUID
    name TEXT NOT NULL,
    git_branch TEXT NOT NULL,         -- Git branch name (e.g. "session-abc123")
    git_remote_url TEXT NOT NULL,     -- Git remote URL
    state TEXT NOT NULL,              -- 'active' | 'suspended' | 'deleted'
    pod_name TEXT,                    -- k8s pod name (null if suspended)
    service_name TEXT,                -- k8s service name (null if suspended)
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    last_commit_sha TEXT,             -- Last git commit SHA
    resource_cpu TEXT DEFAULT "100m", -- e.g. "100m"
    resource_memory TEXT DEFAULT "256Mi" -- e.g. "256Mi"
);
```

**Note**: No artifacts table needed - artifacts are just files in the Git repo!

### 4. Session Pod Specification

**Pod Template with Git & Finalizer**:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ttyd-session-<session-id>
  namespace: ttyd-sessions
  labels:
    app: ttyd-session
    session-id: <session-id>
  finalizers:
  - ttyd-sessions.jomcgi.dev/commit-on-delete  # Custom finalizer
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000

  # Clone Git repo before starting ttyd
  initContainers:
  - name: git-clone
    image: alpine/git:latest
    workingDir: /workspace
    command:
      - sh
      - -c
      - |
        # Clone the session repo
        git clone <GIT_REMOTE_URL> /workspace/session
        cd /workspace/session

        # Checkout session branch (create if doesn't exist)
        git checkout -B <GIT_BRANCH>

        # Configure git
        git config user.name "TTYD Session Manager"
        git config user.email "sessions@jomcgi.dev"

        # Create session metadata file
        cat > .session/metadata.json <<EOF
        {
          "session_id": "<SESSION_ID>",
          "name": "<SESSION_NAME>",
          "created_at": "$(date -Iseconds)",
          "branch": "<GIT_BRANCH>"
        }
        EOF

        # Create .claude directory for context
        mkdir -p .claude
        echo '{"messages": [], "artifacts": []}' > .claude/context.json

        # Initial commit if new branch
        git add .
        git commit -m "Initialize session: <SESSION_NAME>" || true
        git push -u origin <GIT_BRANCH>
    volumeMounts:
    - name: workspace
      mountPath: /workspace
    env:
    - name: GIT_REMOTE_URL
      valueFrom:
        secretKeyRef:
          name: ttyd-git-credentials
          key: remote-url

  containers:
  - name: ttyd
    image: tsl0922/ttyd:alpine  # Smaller image with git
    workingDir: /workspace/session
    command:
      - ttyd
      - -p
      - "7681"
      - -W
      - --writable
      - -t
      - fontSize=14
      - -t
      - theme={"background":"#000000"}
      - bash
      - -l
    ports:
    - containerPort: 7681
      name: http

    # PreStop hook to commit before shutdown
    lifecycle:
      preStop:
        exec:
          command:
            - sh
            - -c
            - |
              cd /workspace/session
              git add -A
              git commit -m "Auto-commit on session suspend/delete at $(date -Iseconds)" || true
              git push origin <GIT_BRANCH>

    volumeMounts:
    - name: workspace
      mountPath: /workspace

    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi

    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: false  # Need writable workspace
      capabilities:
        drop: [ALL]

  volumes:
  - name: workspace
    emptyDir: {}  # Ephemeral! Git is source of truth

  restartPolicy: Never
```

**Service for each pod**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: ttyd-session-<session-id>
  namespace: ttyd-sessions
spec:
  selector:
    session-id: <session-id>
  ports:
  - port: 7681
    targetPort: 7681
  type: ClusterIP
```

**Git Credentials Secret** (created once):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ttyd-git-credentials
  namespace: ttyd-sessions
type: Opaque
stringData:
  remote-url: https://<TOKEN>@github.com/jomcgi/ttyd-sessions.git
  # Or use SSH key
  ssh-key: |
    -----BEGIN OPENSSH PRIVATE KEY-----
    ...
    -----END OPENSSH PRIVATE KEY-----
```

### 5. Git Repository Structure

**Each session gets its own Git branch** in the shared repo:

```
github.com/jomcgi/ttyd-sessions (repo)
├── main (default branch)
│   └── README.md
├── session-abc123 (branch for session abc123)
│   ├── .session/
│   │   └── metadata.json          # Session metadata
│   ├── .claude/
│   │   ├── context.json            # Claude conversation history
│   │   └── artifacts/              # Claude-generated artifacts
│   │       ├── diagram.png
│   │       ├── component.jsx
│   │       └── styles.css
│   ├── work/                       # User's working directory
│   │   ├── project/
│   │   └── notes.md
│   └── .gitignore                  # Ignore temp files
└── session-def456 (another session branch)
    └── ...
```

**Key directories**:
- `.session/` - Session metadata (created by init container)
- `.claude/` - Claude context and artifacts (populated by Claude or user)
- `work/` - User's workspace (can be any structure)

**Commit strategy**:
- Initial commit: Session creation (via initContainer)
- Auto-commits: On suspend/delete (via finalizer + preStop hook)
- Manual commits: User-triggered via API

**Branch naming**: `session-<uuid>` (e.g. `session-a1b2c3d4`)

### 6. Finalizer Workflow (Critical!)

**How finalizers ensure commits before pod deletion**:

1. **Pod created with finalizer**:
   ```yaml
   metadata:
     finalizers:
     - ttyd-sessions.jomcgi.dev/commit-on-delete
   ```

2. **User requests delete/suspend**: API server sends delete request to K8s

3. **Kubernetes marks pod for deletion**: Sets `deletionTimestamp` but **doesn't delete yet**

4. **API server watches for deletionTimestamp**:
   - Detects pod has finalizer
   - Execs into pod to commit: `kubectl exec <pod> -- /bin/sh -c "cd /workspace/session && git add -A && git commit -m 'Final commit' && git push"`
   - Removes finalizer from pod metadata

5. **Kubernetes deletes pod**: Now that finalizer is removed, pod actually deletes

**Fallback**: `preStop` hook also commits (belt + suspenders approach)

### 6. Terminal Access Flow

**User connects to terminal**:
1. Frontend requests `/api/sessions/:id/terminal` (WebSocket)
2. API server looks up pod service name
3. API server opens WebSocket to `ttyd-session-<id>:7681`
4. API server proxies WebSocket bidirectionally
5. User gets interactive terminal in browser

**Alternative (simpler for POC)**:
- API server does `kubectl port-forward` to pod
- Returns temporary URL to frontend
- Frontend connects via proxy URL

## Minimum Feature Set

### Must Have (POC)
- ✅ Create new session (spawns pod + git branch)
- ✅ List sessions with state (query K8s API + SQLite)
- ✅ Switch between sessions (connect to different pods)
- ✅ Suspend session (commit + push + delete pod, keep branch)
- ✅ Resume session (spawn pod, clone from branch)
- ✅ Delete session (commit + push + delete pod + branch)
- ✅ View terminal in UI (WebSocket proxy)
- ✅ Auto-commit on pod deletion (finalizer)
- ✅ Manual commit trigger (API endpoint)
- ✅ View session history (git log)
- ✅ Resource usage (from K8s metrics)

### Nice to Have (Post-POC)
- 🔲 **Claude context preservation**: Store conversation in `.claude/context.json`
- 🔲 **Artifact tracking**: Index files in `.claude/artifacts/` directory
- 🔲 **Auto-suspend inactive**: Watch last activity, auto-commit if idle
- 🔲 **Session export**: `git archive` to tarball
- 🔲 **Search sessions**: Full-text search across commits
- 🔲 **Tmux integration**: True persistence within pod
- 🔲 **Git branch auto-detection**: Show current git branch in UI

### Explicitly Out of Scope (V1)
- ❌ Multi-user support (single user for POC)
- ❌ Authentication (use Cloudflare Access later)
- ❌ Session sharing (could be done via Git branch sharing)
- ❌ Real-time collaboration
- ❌ Automatic Claude context capture (manual for now)

## Implementation Steps

### Phase 1: Git + Kubernetes Integration (Day 1-2)
1. **Setup Go project**
   ```bash
   go mod init github.com/jomcgi/ttyd-session-manager
   go get k8s.io/client-go@latest
   go get github.com/gin-gonic/gin
   go get modernc.org/sqlite
   ```

2. **Create Git repo for sessions**
   ```bash
   # Create repo: github.com/jomcgi/ttyd-sessions
   # Initialize with README
   # Generate PAT with repo permissions
   ```

3. **Kubernetes client setup**
   - Load in-cluster config or kubeconfig
   - Create clientset
   - Test pod creation with git-clone initContainer

4. **Session manager core**
   - Create pod from template with git-clone
   - Create service for pod
   - Add finalizer to pod
   - Track in SQLite (session metadata only)

5. **Basic API endpoints**
   - POST /api/sessions (create pod + git branch)
   - GET /api/sessions (list from K8s + SQLite)
   - DELETE /api/sessions/:id (finalizer → commit → delete pod)

### Phase 2: Finalizer + Terminal (Day 3)
1. **Implement finalizer controller**
   - Watch for pods with `deletionTimestamp`
   - Exec into pod to commit: `git add -A && git commit && git push`
   - Remove finalizer after successful push
   - Handle errors gracefully

2. **WebSocket proxy**
   - Accept WebSocket from frontend
   - Connect to ttyd pod service
   - Bidirectional proxy

3. **Frontend updates**
   - Connect to WebSocket endpoint
   - Render terminal
   - Handle reconnection

4. **Suspend/Resume**
   - Suspend: Finalizer commits → delete pod (keep branch)
   - Resume: Spawn new pod → git-clone pulls branch
   - Update session state in DB

### Phase 3: Git Integration Features (Day 4)
1. **Manual commit endpoint**
   - POST /api/sessions/:id/commit
   - Exec into pod to run git commit + push
   - Return commit SHA

2. **Git history endpoint**
   - GET /api/sessions/:id/git-log
   - Exec `git log --oneline` in pod
   - Return commit history

3. **Session cloning** (optional)
   - POST /api/sessions/:id/clone
   - Create new session from existing branch
   - New pod clones same branch

### Phase 4: Testing & Deployment (Day 5)
1. **Integration tests**
   - Create session → pod appears, branch created
   - Suspend → pod deleted, branch remains, files committed
   - Resume → pod recreated, files restored from git
   - Delete → everything cleaned up

2. **Helm chart**
   - API server deployment
   - RBAC (ServiceAccount, Role, RoleBinding)
   - Service for API server
   - Secret for Git credentials (1Password operator)
   - ConfigMap for pod templates

3. **Deploy to homelab**
   - Create namespace `ttyd-sessions`
   - Create Git credentials secret
   - Deploy via ArgoCD
   - Test end-to-end workflow

## Deployment (Kubernetes)

### Prerequisites
- Kubernetes cluster (homelab)
- kubectl configured
- GitHub account + Personal Access Token (or SSH key)
- Git repo for sessions (e.g. `github.com/jomcgi/ttyd-sessions`)
- Go 1.21+
- Node.js 20+ (for frontend build)

### Namespace Setup
```bash
kubectl create namespace ttyd-sessions
```

### RBAC Configuration
```yaml
# charts/ttyd-session-manager/templates/rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ttyd-session-manager
  namespace: ttyd-sessions
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ttyd-session-manager
  namespace: ttyd-sessions
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log", "pods/exec"]
  verbs: ["create", "get", "list", "delete", "watch"]
- apiGroups: [""]
  resources: ["services"]
  verbs: ["create", "get", "list", "delete"]
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["create", "get", "list", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ttyd-session-manager
  namespace: ttyd-sessions
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: ttyd-session-manager
subjects:
- kind: ServiceAccount
  name: ttyd-session-manager
  namespace: ttyd-sessions
```

### Running Locally (Development)
```bash
# Port-forward to K8s API server (if needed)
# Or use kubeconfig from ~/.kube/config

cd backend
export KUBECONFIG=$HOME/.kube/config
go run main.go
# API server listens on :8080
# Manages pods in ttyd-sessions namespace

cd ../frontend
npm install
npm run dev
# UI on :3000
```

### File Structure
```
ttyd-session-manager/
├── backend/
│   ├── main.go                      # Entry point, HTTP server
│   ├── kubernetes/
│   │   ├── client.go                # K8s client setup
│   │   ├── pod.go                   # Pod lifecycle
│   │   ├── pvc.go                   # PVC management
│   │   └── templates.go             # Pod/Service templates
│   ├── session/
│   │   ├── manager.go               # Session orchestration
│   │   └── storage.go               # SQLite operations
│   ├── artifact/
│   │   ├── handler.go               # HTTP handlers
│   │   └── storage.go               # PVC interaction
│   ├── proxy/
│   │   └── websocket.go             # Terminal WebSocket proxy
│   └── go.mod
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # ttyd-session-manager.jsx
│   │   ├── api.js                   # API client
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── charts/
│   └── ttyd-session-manager/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── deployment.yaml      # API server
│           ├── service.yaml
│           ├── rbac.yaml
│           └── configmap.yaml       # Pod templates
└── README.md
```

## Success Criteria

The POC is successful if:
- ✅ Can create 3+ concurrent sessions (3 pods running)
- ✅ Sessions persist across pod deletion (Git branch retained)
- ✅ Files created in terminal are committed to Git
- ✅ Suspend/resume restores exact file state from Git
- ✅ Terminal is interactive via browser WebSocket
- ✅ Resource usage visible (kubectl top pod)
- ✅ Clean deletion (pod + service removed, branch optional)
- ✅ Finalizer successfully commits before pod deletion
- ✅ Can view session history via `git log`

## Security Considerations

### Pod Security
- Run as non-root user (UID 1000)
- Drop all capabilities
- Resource limits enforced
- Ephemeral storage only (no PVCs)
- Network policies (optional, future)

### Git Credentials
- Store Git credentials in Kubernetes Secret
- Use 1Password operator to inject PAT/SSH key
- Rotate credentials regularly
- Consider using deploy keys (read-only on resume)

### API Security (Future)
- Cloudflare Access for authentication
- RBAC for API endpoints
- Rate limiting per user
- Audit log of all commits

### Data Exposure
- Session data visible in Git repo
- Use private repo
- Consider encrypting sensitive files in Git
- .gitignore for secrets (though pods are ephemeral)

## Known Limitations (POC)

1. **Single namespace** - All sessions in ttyd-sessions namespace
2. **No authentication** - Trust cluster network
3. **No session limits** - Could exhaust cluster resources
4. **Manual Git cleanup** - Old branches accumulate in repo
5. **Basic WebSocket proxy** - No reconnection logic
6. **Commit on every suspend** - Could create many commits
7. **No merge conflict handling** - Assumes single user per session
8. **Git repo size** - Large files bloat the repo (consider Git LFS)
9. **Finalizer timeout** - Long-running commits could fail
10. **No encryption at rest** - Session data visible in Git repo

## Future Enhancements (Post-POC)

### Advanced Git Features
- **Squash commits**: Periodic squashing to reduce branch size
- **Git LFS**: Store large artifacts (images, binaries) efficiently
- **Branch pruning**: Auto-delete branches after N days inactive
- **Encrypted files**: Use git-crypt for sensitive data
- **Commit signing**: GPG-signed commits for audit trail
- **Git hooks**: Pre-commit linting, formatting
- **Diff view**: Show changes before commit in UI

### Advanced Session Features
- **Tmux integration**: True persistence, survive pod crashes
- **Git awareness in terminal**: Show git status in prompt
- **Claude integration**: Auto-commit artifacts with descriptions
- **Session templates**: Predefined environments (Python, Node, Go)
- **Shared sessions**: Multi-user via Git branch sharing
- **Time-travel**: Restore session to any commit
- **Search**: Full-text search across all session files

### Production Readiness
- **Authentication**: Cloudflare Access + JWT
- **Multi-tenancy**: User namespaces, quotas
- **Monitoring**: Prometheus metrics, Grafana dashboards
- **Alerting**: Session stuck, resource exhaustion, commit failures
- **Auto-scaling**: Node autoscaler for session pods
- **Backup**: Git remote already provides backup!

## Timeline

**Total**: 5 days for POC

- Day 1-2: K8s integration + pod lifecycle
- Day 3: Terminal WebSocket proxy
- Day 4: Artifact support
- Day 5: Helm chart + deployment testing

## Next Steps

1. Initialize Go project with client-go
2. Test creating a simple pod from Go
3. Build session manager core (create/list/delete)
4. Implement WebSocket proxy
5. Build frontend integration
6. Create Helm chart
7. Deploy to homelab cluster

## References

- **ttyd**: https://github.com/tsl0922/ttyd
- **client-go**: https://github.com/kubernetes/client-go
- **Longhorn**: https://longhorn.io
- **WebSocket proxy example**: https://github.com/koding/websocketproxy
