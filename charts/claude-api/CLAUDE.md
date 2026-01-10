# Claude API Server

Backend API for Claude Code web interface with WebSocket streaming and voice support.

## Architecture

Single pod deployment with:
- **API Server** (port 3000) - Express + WebSocket server
- **Claude Code** - Max subscription (authenticate via `claude /login`)
- **Session Management** - File-based session persistence on PVC

## Key Files

- `src/src/index.ts` - Main API server (TypeScript)
- `templates/deployment.yaml` - Single pod deployment
- `templates/pvc.yaml` - 200GB Longhorn storage for sessions
- `image/apko.yaml` - Container image definition

## API Endpoints

### REST
- `GET /health` - Health check
- `GET /sessions` - List all sessions
- `POST /sessions` - Create new session
- `GET /sessions/:id` - Get session details
- `DELETE /sessions/:id` - Delete session

### WebSocket
- `ws://host/ws?session=<id>` - Stream Claude Code I/O

## Persistence

PVC mounted at `/home/user` containing:
- `.claude/` - Claude Code OAuth tokens and state
- `.claude-api/sessions/` - Session metadata
- `.npm-global/` - Installed npm packages

## Secrets

From 1Password item `claude-api.jomcgi.dev`:
- `github_token` - Git operations
- `google_api_key` - Gemini API for voice transcription

## Common Tasks

### Initial Setup
```bash
# After first deployment, authenticate Claude Code
kubectl exec -it deploy/claude-api -n claude-api -- claude /login
```

### Check Status
```bash
kubectl logs -n claude-api deploy/claude-api -f
kubectl exec -it deploy/claude-api -n claude-api -- claude /doctor
```
