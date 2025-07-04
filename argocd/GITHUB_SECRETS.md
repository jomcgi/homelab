# Required GitHub Secrets for ArgoCD Bootstrap

This setup requires three GitHub Secrets to be configured in your repository.

## 1. GitHub Personal Access Token

**Secret Name:** `GITHUB_TOKEN`

**Purpose:** Allows ArgoCD to access your private repository for:
- ApplicationSet service discovery
- Repository cloning and manifest synchronization
- Git-based GitOps operations

**How to Create:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Set expiration (recommend 1 year)
4. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `read:org` (Read org and team membership, read org projects)
5. Generate token and copy the value
6. Add to GitHub Secrets as `GITHUB_TOKEN`

## 2. 1Password Connect Host

**Secret Name:** `ONEPASSWORD_CONNECT_HOST`

**Purpose:** 1Password Connect server URL for the operator to fetch secrets

**Value Format:** `https://your-connect-server.com`

**Setup:**
1. Deploy 1Password Connect server (or use hosted version)
2. Get the Connect server URL
3. Add to GitHub Secrets as `ONEPASSWORD_CONNECT_HOST`

## 3. 1Password Connect Token

**Secret Name:** `ONEPASSWORD_CONNECT_TOKEN`

**Purpose:** Authentication token for 1Password Connect API

**How to Create:**
1. In your 1Password Connect server dashboard
2. Create a new Connect token
3. Set appropriate vault permissions
4. Copy the token value
5. Add to GitHub Secrets as `ONEPASSWORD_CONNECT_TOKEN`

## Setting GitHub Secrets

1. Go to your repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add each secret with the exact names above
4. Values should be the actual tokens/URLs (no quotes or extra formatting)

## Verification

You can verify the secrets are set correctly by running the bootstrap workflow in dry-run mode:

```yaml
# In GitHub Actions, trigger the workflow with:
dry_run: true
```

This will validate all configurations without making actual changes.

## Security Notes

- ✅ GitHub tokens are scoped to only required permissions
- ✅ 1Password tokens should have minimal vault access
- ✅ All secrets are encrypted at rest in GitHub
- ✅ Secrets are only exposed to workflow runs
- ⚠️  Rotate tokens regularly (especially GitHub PAT)
- ⚠️  Monitor token usage and access logs