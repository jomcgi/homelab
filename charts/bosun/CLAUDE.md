# Bosun - Developer Guide

Two-pod architecture for Claude Code web interface.

## Architecture

```
Cloudflare Tunnel (SSO) --> bosun-frontend Service (:8080)
                              |
                    Frontend Pod (nginx)
                    |- /          -> static React SPA
                    |- /ws        -> proxy to backend:8000
                    |- /api/*     -> proxy to backend:8000
                    |- /terminal/ -> proxy to backend:7681 (ttyd)
                              |
                    Backend Pod (FastAPI + Claude CLI)
                    |- uvicorn :8000  (Bosun API + WebSocket)
                    |- ttyd :7681     (Web terminal for auth)
                    |- git-sync (bg)  (Golden clone pull loop)
                    |
                    PVC /home/user 200Gi
                    |- .claude/       (Auth + session history)
                    |- .npm-global/   (Claude Code CLI)
                    |- .local/        (pip packages)
                    |- repos/golden/  (Read-only, pulled every 60s)
                    |- repos/sessions/ (Per-session copies)
```

## Auth Flow

Claude Code requires interactive `claude /login` for initial authentication. This is a one-time operation persisted on PVC.

1. Frontend shows "Authenticate" modal when `/api/auth/status` returns unauthenticated
2. Modal embeds iframe to `/terminal/` (ttyd) where user runs `claude /login`
3. Credentials at `~/.claude/auth.json` persist across pod restarts

## Golden Clone Pattern

Each session gets an independent local clone (avoids lock contention with git-sync):

1. **Golden clone** (`/repos/golden`): `git fetch && git reset --hard` every 60s
2. **Session creation**: `git clone --local` golden → `/repos/sessions/<uuid>` (hardlinked objects, independent `.git/`)
3. **Session branches**: `git checkout -b session/<uuid>` in the clone

## Common Operations

```bash
# Check service status
kubectl logs -n bosun deploy/bosun-backend -f
kubectl logs -n bosun deploy/bosun-frontend -f

# Authenticate Claude Code (first deployment)
# Open the Bosun UI and click "Auth" in the sidebar

# Debug backend
kubectl exec -it deploy/bosun-backend -n bosun -- /bin/bash
```
