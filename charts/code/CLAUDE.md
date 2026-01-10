# Claude Code Workspace

Persistent Claude Code environment running on Kubernetes with CUI web interface.

## CRITICAL: Homelab Repository Workflow

**NEVER commit directly to the `main` branch.**

The homelab repo at `~/repos/homelab` is a read-only reference that auto-syncs to `origin/main` every 5 minutes. Any local changes will be discarded by the sync.

### Working with Worktrees (Multi-Agent Safe)

Use the `homelab-worktree` helper to create isolated working directories in `/tmp/`:

```bash
# Create a worktree for your feature branch
homelab-worktree feat/add-new-service

# This creates:
#   /tmp/homelab-feat-add-new-service (working directory)
#   Branch: feat/add-new-service (from origin/main)

# Work in the worktree
cd /tmp/homelab-feat-add-new-service

# Make changes, commit, and push
git add .
git commit -m "Add new service"
git push -u origin feat/add-new-service

# Create PR via GitHub, then merge
```

**Why worktrees?**
- Multiple agents can work on different branches simultaneously
- Each agent gets an isolated `/tmp/` directory
- Main clone stays clean and synced to main
- Worktrees are ephemeral (lost on pod restart, but changes are pushed)

### Cleanup

```bash
# List worktrees
git -C ~/repos/homelab worktree list

# Remove a worktree
git -C ~/repos/homelab worktree remove /tmp/homelab-feat-add-new-service
```

## Architecture

Single pod deployment with:
- **nginx proxy** (port 8080) - Handles automatic cui token injection
- **CUI** (port 3000) - Web UI for Claude Code sessions
- **Claude Code** - Max subscription (authenticate via `claude /login`)
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
- `google_api_key` - Gemini API for opencode/CUI voice

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
