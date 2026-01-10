# Claude Code Workspace

Persistent Claude Code environment running on Kubernetes with CUI web interface.

## Architecture

Single pod deployment with:
- **CUI** (port 3000) - Web UI for Claude Code sessions
- **Claude Code** - Max subscription via OAuth token
- **opencode** - Delegation to vLLM (in-cluster) and Gemini (long context)

## Key Files

- `templates/configmap.yaml` - Init script that installs npm packages and starts cui-server
- `templates/deployment.yaml` - Single pod with ttyd-worker base image
- `templates/pvc.yaml` - 200GB Longhorn storage for persistent state

## Persistence

PVC mounted at `/home/user` containing:
- `.claude/` - Claude Code sessions and OAuth tokens
- `.npm-global/` - Installed npm packages (claude-code, cui-server)
- `.config/opencode/` - opencode configuration
- `repos/` - Git repositories and worktrees

## Secrets

From 1Password item `ttyd-session-manager`:
- `github_token` - Git operations
- `.dockerconfigjson` - GHCR pull secret
- `claude_code_oauth_token` - Claude Max subscription auth
- `google_api_key` - Gemini API for opencode

## Common Tasks

### Initial Setup
```bash
# After first deployment, authenticate Claude Code
kubectl exec -it deploy/code -n code -- claude /login
```

### Check Status
```bash
kubectl logs -n code deploy/code -f
kubectl exec -it deploy/code -n code -- claude /doctor
```

### Access Terminal
```bash
kubectl exec -it deploy/code -n code -- fish
```

### Test opencode delegation
```bash
kubectl exec -it deploy/code -n code -- opencode run "Generate a hello world function"
```
