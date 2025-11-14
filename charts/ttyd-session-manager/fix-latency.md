# TTYD Session Manager - Latency Optimization Tasks

**Goal**: Reduce input lag in terminal sessions from noticeable delay to <50ms

**Current Architecture Issues**:
- Multiple proxy layers adding ~20-40ms each
- String concatenation on every keystroke
- Write deadline syscalls on every WebSocket message

---

## Quick Win #1: Reduce Proxy Hops

**Impact**: Save 2 proxy hops (~40-80ms reduction)

**Current Path**:
```
Browser → Frontend Nginx → Backend Envoy → Backend API → Session Pod Envoy → ttyd
```

**Target Path**:
```
Browser → Frontend Nginx → Session Pod Envoy → ttyd
```

### Tasks

#### Frontend Changes

- [x] **Modify `charts/ttyd-session-manager/frontend/nginx.conf`**
  - Add new location block to proxy WebSocket connections directly to session pods
  - Use Kubernetes DNS to resolve pod service names
  - Example location: `location ~ ^/api/sessions/([^/]+)/terminal$`

- [x] **Update nginx configuration to extract session ID from URL**
  - Use regex capture group to get session ID
  - Proxy to `http://ttyd-session-$1.ttyd-sessions.svc.cluster.local:7681/ws`

- [x] **Configure WebSocket-specific proxy settings**
  - Set `proxy_http_version 1.1`
  - Set upgrade headers: `Upgrade` and `Connection`
  - Remove timeouts or set very high values

#### Backend Changes

- [x] **Modify `charts/ttyd-session-manager/backend/pod_builder.go`**
  - Ensure session pods have a Kubernetes Service (ClusterIP) for DNS resolution
  - Service name format: `ttyd-session-{sessionID}`
  - Port: 7681 (Envoy sidecar)

- [x] **Add Service creation in `createSession` function in `main.go`**
  - Create Service alongside Pod creation
  - Selector: match session-id label
  - ClusterIP type for internal cluster DNS

#### Frontend UI Changes (Optional)

- [ ] **Update `charts/ttyd-session-manager/frontend/index.html`**
  - WebSocket connection can remain the same (nginx handles routing)
  - Or optionally connect directly to `/ws/{sessionId}` endpoint

#### Testing

- [ ] **Test direct connection path**
  - Create new session
  - Connect via WebSocket
  - Measure latency: `wscat -c ws://localhost:8080/api/sessions/{id}/terminal`

- [ ] **Compare old vs new path latency**
  - Use browser DevTools Network tab
  - Measure "Time to first byte" for WebSocket frames

---

## Quick Win #2: Binary WebSocket Messages

**Impact**: Eliminate string operations on every keystroke (~5-15ms reduction)

**Current Issue**: String concatenation on every keystroke in frontend

### Tasks

#### Frontend Changes

- [x] **Modify `charts/ttyd-session-manager/frontend/index.html`** (around line 200-240)
  - Replace string concatenation with binary Uint8Array construction
  - Use `TextEncoder` for efficient string-to-bytes conversion

- [x] **Update `term.onData()` handler**
  ```javascript
  // OLD (slow):
  term.onData((data) => {
    const message = '0' + data;
    ws.send(message);
  });

  // NEW (fast):
  const encoder = new TextEncoder();
  term.onData((data) => {
    const encoded = encoder.encode(data);
    const message = new Uint8Array(encoded.length + 1);
    message[0] = 48; // ASCII '0' for ttyd INPUT message type
    message.set(encoded, 1);
    ws.send(message.buffer);
  });
  ```

- [x] **Update resize message handler** (around line 260-270)
  ```javascript
  // Convert resize JSON to binary format
  const resizeJson = JSON.stringify({ columns: term.cols, rows: term.rows });
  const encoded = encoder.encode(resizeJson);
  const resizeMessage = new Uint8Array(encoded.length + 1);
  resizeMessage[0] = 49; // ASCII '1' for ttyd RESIZE message type
  resizeMessage.set(encoded, 1);
  ws.send(resizeMessage.buffer);
  ```

#### Backend Changes

- [x] **Verify `main.go` WebSocket proxy handles binary messages**
  - Check line 380-420 in `terminalWebSocket` function
  - Ensure `websocket.BinaryMessage` is handled alongside `websocket.TextMessage`
  - Current code should work, but verify both message types are proxied

#### Testing

- [ ] **Test binary message transmission**
  - Open browser DevTools → Network → WS
  - Verify messages show as "Binary" not "Text"
  - Test typing, special characters, and resize events

- [ ] **Measure encoding overhead reduction**
  - Use browser Performance API to measure encoding time
  - Should see <1ms encoding time consistently

---

## Quick Win #3: Remove Write Deadline Overhead

**Impact**: Eliminate syscall overhead on every write (~2-10ms reduction per message)

**Current Issue**: Setting write deadline on every WebSocket message adds syscall overhead

### Tasks

#### Backend Changes - WebSocket Proxy Functions

- [x] **Modify `charts/ttyd-session-manager/backend/main.go`** - `terminalWebSocket` function (around line 380-450)

- [x] **Remove write deadline from client → ttyd direction** (line ~400)
  ```go
  // OLD (adds overhead):
  if err := ttydConn.SetWriteDeadline(time.Now().Add(writeDeadline)); err != nil {
    errChan <- fmt.Errorf("ttyd set write deadline error: %w", err)
    return
  }

  // NEW (remove deadline setting):
  // Remove the SetWriteDeadline call entirely
  ```

- [x] **Remove write deadline from ttyd → client direction** (line ~420)
  ```go
  // OLD (adds overhead):
  if err := conn.SetWriteDeadline(time.Now().Add(writeDeadline)); err != nil {
    errChan <- fmt.Errorf("client set write deadline error: %w", err)
    return
  }

  // NEW (remove deadline setting):
  // Remove the SetWriteDeadline call entirely
  ```

- [x] **Repeat for `proxyWebSocket` function** (around line 480-550)
  - Same changes: remove both SetWriteDeadline calls

#### Alternative Approach (If Deadlines Are Required)

- [ ] **Option: Set deadline once at connection start**
  ```go
  // Set a very long deadline once (e.g., 1 hour)
  conn.SetWriteDeadline(time.Now().Add(1 * time.Hour))
  ttydConn.SetWriteDeadline(time.Now().Add(1 * time.Hour))
  // Then remove per-message deadline setting
  ```

#### Error Handling

- [x] **Update error messages**
  - Remove deadline-related error text
  - Keep the actual write error handling

- [ ] **Consider connection monitoring**
  - Add ping/pong mechanism if needed for dead connection detection
  - Use `SetPongHandler` instead of write deadlines

#### Testing

- [ ] **Test connection stability without deadlines**
  - Create session and keep terminal open for 5+ minutes
  - Verify no connection drops or hangs

- [ ] **Test with network issues**
  - Simulate slow client (Chrome DevTools → Network throttling)
  - Verify graceful handling without deadlines

- [ ] **Measure latency improvement**
  - Use `strace` on backend pod to verify no `setsockopt` calls
  - Measure round-trip time for keystroke → echo

---

## Validation & Measurement

### Before Optimization

- [ ] **Baseline measurement**
  - Record average keystroke latency (time from keypress to character appearing)
  - Use browser DevTools Performance recording
  - Target metric: measure 50+ keystrokes

### After Each Quick Win

- [ ] **Quick Win #1 measurement**
  - Expected: 40-80ms improvement
  - Test: Type rapidly and measure lag

- [ ] **Quick Win #2 measurement**
  - Expected: 5-15ms improvement
  - Test: Check DevTools for message encoding time

- [ ] **Quick Win #3 measurement**
  - Expected: 2-10ms improvement per message
  - Test: Profile syscall overhead reduction

### Overall Target

- [ ] **Achieve <50ms end-to-end latency**
  - From keypress to character appearing in terminal
  - Should feel instantaneous to user

---

## Rollback Plan

If any optimization causes issues:

- [ ] **Quick Win #1 Rollback**: Revert nginx config to proxy through backend API
- [ ] **Quick Win #2 Rollback**: Revert to string concatenation in frontend
- [ ] **Quick Win #3 Rollback**: Restore write deadline calls

---

## Additional Considerations

### tmux Latency (Future Optimization)

- [ ] **Measure tmux overhead** (not in quick wins, but worth testing)
  - Create test session without tmux wrapper
  - Compare latency directly running shell
  - If significant (>20ms), consider making tmux optional

### Envoy Buffer Tuning

- [ ] **Add buffer limits to Envoy configs** (if needed after quick wins)
  - Modify `charts/ttyd-session-manager/templates/envoy-configmap.yaml`
  - Add `per_connection_buffer_limit_bytes: 32768` to both backend and session Envoy

---

## Success Criteria

- [ ] **Latency reduced from noticeable to imperceptible** (<50ms target)
- [ ] **All existing functionality preserved** (no regressions)
- [ ] **Sessions remain stable** (no new disconnection issues)
- [ ] **Measurements documented** (before/after metrics recorded)