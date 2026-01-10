# Claude Web Interface

Claude Code web interface with React frontend, WebSocket streaming, and voice support.

## Architecture

Single pod deployment with:
- **Frontend** (React + Vite) - Served at `/`
- **API Server** (Express) - Endpoints at `/api/*`
- **WebSocket** - Claude Code streaming at `/ws`
- **Claude Code** - Max subscription (authenticate via `claude /login`)
- **Session Management** - File-based session persistence on PVC

## Key Files

- `frontend/` - React frontend (Vite + Tailwind)
- `src/src/index.ts` - Express API server
- `templates/deployment.yaml` - Single pod deployment
- `templates/pvc.yaml` - 200GB Longhorn storage for sessions
- `image/apko.yaml` - Container image definition

## API Endpoints

### REST
- `GET /api/health` - Health check
- `GET /api/sessions` - List all sessions
- `POST /api/sessions` - Create new session
- `GET /api/sessions/:id` - Get session details
- `DELETE /api/sessions/:id` - Delete session

### WebSocket
- `ws://host/ws?session=<id>` - Stream Claude Code I/O

## Persistence

PVC mounted at `/home/user` containing:
- `.claude/` - Claude Code OAuth tokens and state
- `.claude-api/sessions/` - Session metadata
- `.npm-global/` - Installed npm packages

## Secrets

From 1Password item `claude.jomcgi.dev`:
- `github_token` - Git operations
- `google_api_key` - Gemini API for voice transcription

## Common Tasks

### Initial Setup
```bash
# After first deployment, authenticate Claude Code
kubectl exec -it deploy/claude -n claude -- claude /login
```

### Check Status
```bash
kubectl logs -n claude deploy/claude -f
kubectl exec -it deploy/claude -n claude -- claude /doctor
```
