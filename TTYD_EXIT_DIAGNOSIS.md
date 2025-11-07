# TTYD Immediate Exit - Root Cause Analysis

**Issue**: When connecting to a ttyd session pod, ttyd immediately exits
**Reported**: 2025-11-07
**Severity**: HIGH - Blocks all terminal access

---

## Quick Answer

**The problem is most likely one of these three issues:**

1. ❌ **Wrong image being used** - `ttyd.Dockerfile` instead of the correct `apko_image` build
2. ❌ **InitContainer failed** - `/workspace/session` directory doesn't exist
3. ❌ **opencode can't start** - Missing dependencies, wrong working directory, or permissions

---

## Background: Two Image Build Processes

### ✅ CORRECT: Bazel `apko_image` (Production)

**Location**: `charts/ttyd-session-manager/backend/BUILD`

```starlark
apko_image(
    name = "ttyd_worker_image",
    config = "apko.yaml",              # Wolfi Linux base
    contents = "@ttyd_lock//:contents",
    multiarch_tars = [
        "@ttyd//:tar",                  # ttyd v1.7.7 from GitHub
        "@opencode//:tar",              # opencode v1.0.39 from GitHub
    ],
    repository = "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker",
    tars = [
        ":fish_config_tar",             # Fish shell config
        ":opencode_config_tar",         # OpenCode provider config
    ],
)
```

**Includes**:
- ✅ Wolfi Linux base (not Alpine)
- ✅ ttyd binary (from https://github.com/tsl0922/ttyd/releases/download/1.7.7/)
- ✅ opencode binary (from https://github.com/sst/opencode/releases/download/v1.0.39/)
- ✅ Fish shell, Bazelisk, kubectl, helm, etc.
- ✅ OpenCode config at `/home/user/.config/opencode/opencode.json`
- ✅ Non-root user (UID 1000)

**Build command**:
```bash
bazel build --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image
bazel run --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image.push
```

### ❌ INCORRECT: `ttyd.Dockerfile` (Legacy/Unused)

**Location**: `charts/ttyd-session-manager/backend/ttyd.Dockerfile`

**Includes**:
- ❌ Alpine Linux base (not Wolfi)
- ✅ ttyd binary (via apk)
- ❌ **NO opencode binary** (missing!)
- ✅ Fish shell, git, basic tools
- ❌ Runs as root by default

**Default CMD**: `["ttyd", "-p", "7681", "-W", "--writable", "fish"]`

**Problem**: This image does NOT contain the `opencode` binary that the pod spec tries to run!

---

## How the Pod is Configured

From `charts/ttyd-session-manager/backend/main.go:326-336`:

```go
{
    Name:  "ttyd",
    Image: fmt.Sprintf("ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:%s", imageTag),
    Command: []string{
        "ttyd",
        "-p", "7682",
        "-W",
        "--writable",
        "-o", "disableLeaveAlert=true",
        "-o", "rendererType=dom",
        "opencode",  // ← THIS IS THE COMMAND TTYD RUNS
    },
    WorkingDir: "/workspace/session",  // ← MUST EXIST
    ...
}
```

**What this means**:
- ttyd spawns `opencode` as a child process
- If `opencode` binary doesn't exist → ttyd exits immediately
- If `opencode` exits → ttyd exits too
- Pod has `RestartPolicy: Never` → pod dies forever

---

## Root Cause Analysis

### Scenario 1: Wrong Image Being Used ❌

**Symptoms**:
- ttyd exits immediately when connection attempted
- No error logs (just silent exit)
- Pod shows as Running but ttyd container is dead

**Diagnosis**:
```bash
# Check which image is actually running
kubectl get pod ttyd-session-{ID} -n ttyd-sessions -o jsonpath='{.spec.containers[?(@.name=="ttyd")].image}'

# Should be:
# ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:{git-hash}

# If it shows a different tag, the wrong image was pushed
```

**Root cause**: The `ttyd.Dockerfile` image was pushed instead of the Bazel-built `apko_image`.

**Fix**: Rebuild and push the correct image:
```bash
cd /home/user/homelab
bazel build --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image
bazel run --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image.push
```

---

### Scenario 2: InitContainer Failed ❌

**Symptoms**:
- Pod shows as Running but ttyd exits on connection
- InitContainer logs show git clone failure
- `/workspace/session` directory doesn't exist

**Diagnosis**:
```bash
# Check initContainer logs
kubectl logs ttyd-session-{ID} -n ttyd-sessions -c git-clone

# Expected output:
# "Session initialized and pushed to branch: session-{ID}"

# If it shows errors, git clone failed
```

**Root cause**: InitContainer failed to clone repo or create `/workspace/session`.

**Common causes**:
- GitHub token invalid/expired
- Git remote unreachable
- Branch already exists (name collision)
- Permissions issue

**Fix**: Delete pod and recreate session with new ID:
```bash
kubectl delete pod ttyd-session-{ID} -n ttyd-sessions
# Create new session via API
```

---

### Scenario 3: opencode Fails to Start ❌

**Symptoms**:
- Pod is Running
- opencode binary exists
- `/workspace/session` exists
- But ttyd still exits on connection

**Diagnosis**:
```bash
# Exec into pod to test opencode manually
kubectl exec -it ttyd-session-{ID} -n ttyd-sessions -c ttyd -- sh

# Try to run opencode
cd /workspace/session
opencode --version

# If this fails, check:
which opencode              # Should be /usr/local/bin/opencode
ls -la /workspace/session   # Should show git repo contents
id                          # Should be uid=1000(user)
```

**Possible causes**:
- opencode config missing (should be at `/home/user/.config/opencode/opencode.json`)
- Working directory is empty (initContainer didn't finish)
- Permissions wrong (opencode not executable)
- opencode requires TTY but running in non-interactive mode

**Fix**: Depends on root cause found above.

---

### Scenario 4: Working Directory Timing Issue ❌

**Symptoms**:
- First connection fails (ttyd exits)
- Subsequent connections might work
- Race condition between initContainer and main container

**Root cause**: The ttyd container starts before initContainer finishes cloning the repo.

**Evidence**: Recent commit `2b707ff` mentions "use correct working directory /workspace/session"

**Fix**: Add initContainer completion check or use a different approach:

**Option A**: Change working directory temporarily
```go
// In main.go, change WorkingDir to /workspace temporarily
WorkingDir: "/workspace",
Command: []string{
    "ttyd",
    "-p", "7682",
    "-W",
    "--writable",
    "-o", "disableLeaveAlert=true",
    "-o", "rendererType=dom",
    "sh", "-c", "cd session && opencode",  // ← cd first, then run opencode
},
```

**Option B**: Use Pod readiness gate
```go
// Add readiness probe to ensure /workspace/session exists
ReadinessProbe: &corev1.Probe{
    Exec: &corev1.ExecAction{
        Command: []string{"test", "-d", "/workspace/session"},
    },
    InitialDelaySeconds: 5,
    PeriodSeconds: 2,
},
```

---

## Diagnostic Commands

### 1. Check which image is running
```bash
kubectl get pod ttyd-session-{ID} -n ttyd-sessions -o jsonpath='{.spec.containers[?(@.name=="ttyd")].image}'
```

### 2. Check pod status and events
```bash
kubectl describe pod ttyd-session-{ID} -n ttyd-sessions
```

### 3. Check initContainer logs
```bash
kubectl logs ttyd-session-{ID} -n ttyd-sessions -c git-clone
```

### 4. Check ttyd container logs
```bash
kubectl logs ttyd-session-{ID} -n ttyd-sessions -c ttyd
```

### 5. Check if opencode exists in the image
```bash
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- which opencode
```

### 6. Check working directory contents
```bash
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- ls -la /workspace/session
```

### 7. Test opencode manually
```bash
kubectl exec -it ttyd-session-{ID} -n ttyd-sessions -c ttyd -- sh -c "cd /workspace/session && opencode --version"
```

### 8. Check if ttyd is actually running
```bash
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- ps aux | grep ttyd
```

---

## Recommended Fix (Quick Win)

Based on the analysis, the **most likely** issue is **Scenario 4** (working directory timing).

### Immediate Fix: Change ttyd command to handle missing directory

**File**: `charts/ttyd-session-manager/backend/main.go:328-336`

**Current**:
```go
Command: []string{
    "ttyd",
    "-p", "7682",
    "-W",
    "--writable",
    "-o", "disableLeaveAlert=true",
    "-o", "rendererType=dom",
    "opencode",
},
WorkingDir: "/workspace/session",
```

**Proposed**:
```go
Command: []string{
    "ttyd",
    "-p", "7682",
    "-W",
    "--writable",
    "-o", "disableLeaveAlert=true",
    "-o", "rendererType=dom",
    "sh", "-c", "while [ ! -d /workspace/session ]; do sleep 1; done && cd /workspace/session && exec opencode",
},
WorkingDir: "/workspace",  // Start in /workspace, wait for session/ to exist
```

**What this does**:
1. Starts ttyd in `/workspace` (always exists)
2. Waits for `/workspace/session` to be created by initContainer
3. Changes to `/workspace/session`
4. Runs `opencode` with `exec` (replaces shell, so ttyd sees opencode as direct child)

---

## Long-term Solution

### 1. Add health checks to ttyd container

```go
LivenessProbe: &corev1.Probe{
    HTTPGet: &corev1.HTTPGetAction{
        Path: "/",
        Port: intstr.FromInt(7682),
    },
    InitialDelaySeconds: 10,
    PeriodSeconds: 10,
},
ReadinessProbe: &corev1.Probe{
    Exec: &corev1.ExecAction{
        Command: []string{"test", "-d", "/workspace/session"},
    },
    InitialDelaySeconds: 5,
    PeriodSeconds: 2,
},
```

### 2. Use emptyDir volume with init completion marker

```go
// In initContainer, create marker file when done
echo "ready" > /workspace/.init-complete

// In ttyd command, wait for marker
"sh", "-c", "while [ ! -f /workspace/.init-complete ]; do sleep 1; done && cd session && exec opencode"
```

### 3. Consider using a startup script

Create a script in the image that handles initialization:

```bash
#!/bin/sh
# /usr/local/bin/start-session.sh

# Wait for git clone to complete
while [ ! -d /workspace/session/.git ]; do
    echo "Waiting for git clone to complete..."
    sleep 1
done

# Verify opencode config exists
if [ ! -f /home/user/.config/opencode/opencode.json ]; then
    echo "ERROR: OpenCode config not found"
    exit 1
fi

# Start opencode in the session directory
cd /workspace/session
exec opencode
```

Then use:
```go
Command: []string{
    "ttyd",
    "-p", "7682",
    "-W",
    "--writable",
    "-o", "disableLeaveAlert=true",
    "-o", "rendererType=dom",
    "/usr/local/bin/start-session.sh",
},
```

---

## Testing Plan

After implementing the fix:

1. **Create a new session**:
   ```bash
   curl -X POST http://localhost:8083/api/sessions \
     -H "Content-Type: application/json" \
     -d '{"display_name": "Test ttyd Fix"}'
   ```

2. **Watch pod startup**:
   ```bash
   kubectl get pod ttyd-session-{ID} -n ttyd-sessions -w
   ```

3. **Check initContainer completes**:
   ```bash
   kubectl logs ttyd-session-{ID} -n ttyd-sessions -c git-clone --follow
   ```

4. **Check ttyd logs**:
   ```bash
   kubectl logs ttyd-session-{ID} -n ttyd-sessions -c ttyd --follow
   ```

5. **Connect via WebSocket**:
   ```javascript
   const ws = new WebSocket('ws://localhost:8083/api/sessions/{ID}/terminal');
   ws.onopen = () => console.log('Connected!');
   ws.onmessage = (e) => console.log(e.data);
   ```

6. **Verify terminal is interactive**:
   - Type commands
   - See output
   - Terminal stays connected

---

## Summary

**Problem**: ttyd exits immediately when connection attempted

**Most likely cause**: Race condition between initContainer (creating `/workspace/session`) and ttyd container (trying to start opencode in `/workspace/session`)

**Evidence**: Recent commit `2b707ff` fixed working directory, suggesting this was a known issue

**Recommended fix**: Modify ttyd command to wait for `/workspace/session` to exist before starting opencode

**Alternative causes** (less likely):
- Wrong image being used (missing opencode binary)
- InitContainer failed (git clone error)
- opencode requires something not available in environment

**Next steps**:
1. Run diagnostic commands to confirm root cause
2. Implement recommended fix
3. Test with new session
4. Add health checks for production

---

**Diagnosis completed**: 2025-11-07
**Files analyzed**:
- `charts/ttyd-session-manager/backend/main.go` (pod definition)
- `charts/ttyd-session-manager/backend/BUILD` (correct image build)
- `charts/ttyd-session-manager/backend/ttyd.Dockerfile` (incorrect/legacy image)
- `charts/ttyd-session-manager/backend/apko.yaml` (image config)
- `MODULE.bazel` (opencode and ttyd download config)
