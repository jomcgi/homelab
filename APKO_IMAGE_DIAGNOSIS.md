# APKO Image Diagnosis - ttyd Exit Issue

**Focus**: Since `ttyd.Dockerfile` has been removed, the problem MUST be with the apko image build.

**Date**: 2025-11-07

---

## Potential Issues with APKO Image

### 1. Binary Extraction from Zip Archives ⚠️

**Issue**: The `opencode` binary is downloaded as a zip file and extracted. If the zip structure doesn't match expectations, extraction fails silently.

**Current extraction logic** (from `multiarch_http_archive.bzl:109`):
```python
repository_ctx.execute(["cp", "amd64_extracted/" + extracted_binary_name, "amd64_binary"])
```

**Assumptions**:
- The zip contains a file named `opencode` at the root
- If the actual structure is `opencode-linux-x64/opencode` or has a different name, the `cp` command fails

**Diagnostic**:
```bash
# Download and inspect the zip locally
curl -LO https://github.com/sst/opencode/releases/download/v1.0.39/opencode-linux-x64.zip
unzip -l opencode-linux-x64.zip

# Check what's actually in the zip
unzip opencode-linux-x64.zip
ls -la
```

**Expected**: A file named `opencode` at the root
**If different**: Update `MODULE.bazel` with `extracted_binary_name` parameter

---

### 2. Binary Installation Paths

**Configuration**:

From `MODULE.bazel`:
- **ttyd**: No `package_dir` specified → defaults to `/usr/local/bin`
- **opencode**: `package_dir = "/usr/local/bin"` (explicit)

From `apko.yaml:41`:
- **PATH**: `/usr/local/lib/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`

**Expected locations**:
- `/usr/local/bin/ttyd` (executable, mode 0755)
- `/usr/local/bin/opencode` (executable, mode 0755)

**Diagnostic** (run inside a pod):
```bash
# Check if binaries exist
which ttyd
which opencode

# Check permissions
ls -la /usr/local/bin/ttyd
ls -la /usr/local/bin/opencode

# Check if they're executable
file /usr/local/bin/ttyd
file /usr/local/bin/opencode

# Try to run them
ttyd --version
opencode --version
```

---

### 3. Dynamic Library Dependencies

**Issue**: Both `ttyd` and `opencode` might be dynamically linked binaries requiring specific shared libraries.

**Diagnostic**:
```bash
# Check dynamic dependencies
ldd /usr/local/bin/ttyd
ldd /usr/local/bin/opencode

# Common missing libraries:
# - libc.so.6 (glibc)
# - libssl.so.3 (OpenSSL)
# - libcrypto.so.3 (OpenSSL)
# - libz.so.1 (zlib)
```

**If libraries are missing**: Add them to `apko.yaml` packages section.

**Wolfi packages to check**:
- `glibc` (should be included by default)
- `libssl3` (OpenSSL)
- `libcrypto3` (OpenSSL)
- `zlib` (compression library)

---

### 4. Working Directory Race Condition

**Issue**: The ttyd container starts with `WorkingDir: "/workspace/session"`, but this directory is created by the initContainer.

**Current pod definition** (`main.go:337`):
```go
WorkingDir: "/workspace/session",  // ← May not exist yet
```

**apko.yaml** only creates:
```yaml
paths:
  - path: /workspace
    type: directory
    uid: 1000
    gid: 1000
    permissions: 0o755
```

It does NOT create `/workspace/session` - that's done by the initContainer.

**What happens**:
1. Pod starts
2. Kubernetes starts initContainer (git-clone) and main containers (envoy, ttyd) **in parallel**
3. ttyd tries to start in `/workspace/session` before initContainer creates it
4. Working directory doesn't exist → ttyd fails to start
5. ttyd exits → pod stays in Running state but terminal doesn't work

**Diagnostic**:
```bash
# Check if initContainer completed successfully
kubectl logs ttyd-session-{ID} -n ttyd-sessions -c git-clone

# Expected last line:
# "Session initialized and pushed to branch: session-{ID}"

# Check if /workspace/session exists in ttyd container
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- ls -la /workspace/

# If session/ doesn't exist, initContainer hasn't finished or failed
```

---

### 5. OpenCode Configuration Issues

**Configuration file**: `/home/user/.config/opencode/opencode.json`

**Potential issues**:
- File not created in the right location
- Malformed JSON
- Provider API endpoints unreachable from pod
- Missing environment variables (API keys)

**Diagnostic**:
```bash
# Check if config file exists
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- \
  cat /home/user/.config/opencode/opencode.json

# Check if environment variables are set
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- env | grep -E 'ANTHROPIC|GOOGLE|BUILDBUDDY'

# Try to run opencode manually
kubectl exec -it ttyd-session-{ID} -n ttyd-sessions -c ttyd -- sh
cd /workspace/session
opencode --version
opencode  # See what error it gives
```

---

### 6. TTY/Terminal Issues

**Issue**: ttyd expects to run a command that can attach to a terminal. If `opencode` doesn't support TTY mode, it might exit immediately.

**Pod configuration** (`main.go:329-335`):
```go
Command: []string{
    "ttyd",
    "-p", "7682",
    "-W",              // Allow write access
    "--writable",      // Allow write access (duplicate?)
    "-o", "disableLeaveAlert=true",
    "-o", "rendererType=dom",
    "opencode",        // ← Command ttyd runs
},
```

**Diagnostic**:
```bash
# Check ttyd logs for errors
kubectl logs ttyd-session-{ID} -n ttyd-sessions -c ttyd

# Common errors:
# - "failed to create pty"
# - "command not found"
# - "permission denied"
# - "No such file or directory"

# Try running ttyd manually with a simpler command
kubectl exec -it ttyd-session-{ID} -n ttyd-sessions -c ttyd -- \
  ttyd -p 7683 -W --writable fish
```

---

### 7. User Permissions Issues

**apko.yaml configuration**:
```yaml
accounts:
  users:
    - username: user
      uid: 1000
      gid: 1000
  run-as: 1000
```

**Pod SecurityContext** (`main.go:179-183`):
```go
SecurityContext: &corev1.PodSecurityContext{
    RunAsNonRoot: boolPtr(true),
    RunAsUser:    int64Ptr(1000),
    FSGroup:      int64Ptr(1000),
},
```

**Potential issue**: File ownership mismatches between initContainer and ttyd container.

**Diagnostic**:
```bash
# Check who owns /workspace/session
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- \
  ls -la /workspace/

# Should show:
# drwxr-xr-x  user user  session/

# Check process user
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- id
# Should show: uid=1000(user) gid=1000(user)

# Check if user can write to /workspace/session
kubectl exec ttyd-session-{ID} -n ttyd-sessions -c ttyd -- \
  touch /workspace/session/test.txt
```

---

## Diagnostic Plan

### Step 1: Verify Image Build

```bash
# Build the apko image locally to inspect it
cd /home/user/homelab
bazel build --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image

# Load the image into a local container runtime
# (This depends on your setup - Docker, Podman, etc.)

# Run the image interactively
docker run -it --rm \
  --entrypoint /bin/sh \
  ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:latest

# Inside the container:
which ttyd
which opencode
ttyd --version
opencode --version
ls -la /usr/local/bin/
```

### Step 2: Check Running Pod

```bash
# Get a running pod ID
SESSION_ID=$(kubectl get pods -n ttyd-sessions -l app=ttyd-session -o jsonpath='{.items[0].metadata.labels.session-id}')
POD_NAME="ttyd-session-${SESSION_ID}"

# Check pod status
kubectl get pod $POD_NAME -n ttyd-sessions

# Check container statuses
kubectl get pod $POD_NAME -n ttyd-sessions -o jsonpath='{.status.containerStatuses[*].name}'

# Check ttyd container specifically
kubectl get pod $POD_NAME -n ttyd-sessions -o jsonpath='{.status.containerStatuses[?(@.name=="ttyd")]}'

# Check for restart count (should be 0 with RestartPolicy: Never)
kubectl get pod $POD_NAME -n ttyd-sessions -o jsonpath='{.status.containerStatuses[?(@.name=="ttyd")].restartCount}'
```

### Step 3: Check Logs

```bash
# InitContainer logs
kubectl logs $POD_NAME -n ttyd-sessions -c git-clone

# ttyd container logs
kubectl logs $POD_NAME -n ttyd-sessions -c ttyd

# Envoy sidecar logs (might have proxy errors)
kubectl logs $POD_NAME -n ttyd-sessions -c envoy
```

### Step 4: Exec into Pod and Debug

```bash
# Exec into ttyd container
kubectl exec -it $POD_NAME -n ttyd-sessions -c ttyd -- /bin/sh

# Once inside:
# Check environment
env | sort

# Check working directory
pwd
ls -la

# Check binaries
which ttyd
which opencode
file /usr/local/bin/ttyd
file /usr/local/bin/opencode
ldd /usr/local/bin/ttyd
ldd /usr/local/bin/opencode

# Check if opencode works
cd /workspace
opencode --version
opencode --help

# Check if ttyd can start opencode
ttyd -p 7683 -W --writable opencode &
sleep 2
curl http://localhost:7683/

# Check processes
ps aux | grep -E 'ttyd|opencode'
```

### Step 5: Test opencode in /workspace/session

```bash
# Create test directory if it doesn't exist
mkdir -p /workspace/session
cd /workspace/session

# Initialize a git repo (if not already done)
git init

# Try running opencode
opencode --version

# Try running ttyd with opencode
ttyd -p 7683 -W --writable opencode &
sleep 2

# Check if ttyd is running
ps aux | grep ttyd

# Try connecting via WebSocket
# (This requires a WebSocket client, not available in sh)
```

---

## Likely Root Causes (Ranked)

### 1. **Working Directory Race Condition** (90% likely) 🔴

The ttyd container tries to start in `/workspace/session` before the initContainer creates it.

**Evidence**:
- Recent commit `2b707ff` mentions working directory fix
- initContainers and main containers start in parallel in Kubernetes
- `/workspace/session` is not pre-created in apko.yaml

**Fix**: See "Recommended Fix" section below

### 2. **opencode Binary Not Extracted Correctly** (60% likely) 🟡

The zip file structure might not match expectations, causing the binary extraction to fail.

**Evidence**:
- opencode downloaded as zip, not raw binary
- Extraction assumes binary at root of zip
- Silent failure if cp command fails

**Fix**: Verify zip contents and update `extracted_binary_name` if needed

### 3. **Missing Dynamic Libraries** (30% likely) 🟡

opencode or ttyd might require libraries not included in the Wolfi base.

**Evidence**:
- Binaries might be dynamically linked
- Wolfi is minimal by design

**Fix**: Add missing packages to `apko.yaml`

### 4. **OpenCode Configuration Issues** (20% likely) 🟢

OpenCode might fail to start due to config problems.

**Evidence**:
- Config references API endpoints and env vars
- Depends on 1Password secrets being injected correctly

**Fix**: Verify config file and environment variables

---

## Recommended Fixes

### Fix #1: Working Directory Race Condition (Immediate)

**File**: `charts/ttyd-session-manager/backend/main.go:328-337`

**Change from**:
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

**Change to**:
```go
Command: []string{
    "ttyd",
    "-p", "7682",
    "-W",
    "--writable",
    "-o", "disableLeaveAlert=true",
    "-o", "rendererType=dom",
    "/bin/sh", "-c",
    "while [ ! -d /workspace/session ]; do sleep 0.5; done && cd /workspace/session && exec opencode",
},
WorkingDir: "/workspace",
```

**What this does**:
1. Start ttyd in `/workspace` (always exists)
2. Wait for initContainer to create `/workspace/session`
3. Change to that directory
4. Run opencode with `exec` (replaces shell, proper signal handling)

---

### Fix #2: Verify opencode Zip Extraction

**Check the zip structure**:
```bash
# Download the opencode release
curl -LO https://github.com/sst/opencode/releases/download/v1.0.39/opencode-linux-x64.zip

# List contents
unzip -l opencode-linux-x64.zip
```

**If the binary is NOT at the root**, update `MODULE.bazel`:
```python
multiarch_http_archive(
    name = "opencode",
    amd64_sha256 = "abd7292146d3293b3347ebad84de36fa0689a7850cea53df64c73506cc463072",
    amd64_url = "https://github.com/sst/opencode/releases/download/v1.0.39/opencode-linux-x64.zip",
    arm64_sha256 = "02ca134403781337240a6308c87ee2fc515cca77c5a32e2fae859aa1540d3e44",
    arm64_url = "https://github.com/sst/opencode/releases/download/v1.0.39/opencode-linux-arm64.zip",
    binary_name = "opencode",
    extracted_binary_name = "dist/opencode",  # ← Add this if binary is in dist/
    package_dir = "/usr/local/bin",
)
```

---

### Fix #3: Add Missing Libraries

**If `ldd` shows missing libraries**, update `apko.yaml`:

```yaml
packages:
  # ... existing packages ...
  - glibc            # Usually already included
  - libssl3          # OpenSSL 3.x
  - libcrypto3       # Crypto library
  - zlib             # Compression
  - ca-certificates  # Already included
```

Then rebuild the image:
```bash
bazel build --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image
bazel run --stamp //charts/ttyd-session-manager/backend:ttyd_worker_image.push
```

---

### Fix #4: Add Health Checks

**Add readiness probe to ensure initialization completes**:

```go
// In main.go, ttyd container spec:
ReadinessProbe: &corev1.Probe{
    Exec: &corev1.ExecAction{
        Command: []string{
            "/bin/sh", "-c",
            "test -d /workspace/session && test -f /workspace/session/.git/config",
        },
    },
    InitialDelaySeconds: 2,
    PeriodSeconds: 2,
    TimeoutSeconds: 1,
    FailureThreshold: 30,  // 60 seconds total (30 * 2s)
},
```

This ensures the pod isn't marked Ready until initContainer completes.

---

## Next Steps

1. **Run diagnostic commands** on an existing pod to confirm root cause
2. **Implement Fix #1** (working directory race condition)
3. **Verify opencode zip structure** and implement Fix #2 if needed
4. **Test with new session** to confirm fix works
5. **Add health checks** (Fix #4) for production reliability

---

**Analysis Date**: 2025-11-07
**Confidence**: Working directory race condition is the most likely issue (90%)
**Recommended Action**: Implement Fix #1 immediately and test
