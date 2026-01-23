# Security Audit: Pre-Public Repository Review

## Summary

The repository demonstrates **strong security practices** - all production credentials are properly managed through 1Password OnePasswordItem CRDs. However, there are several categories of sensitive information to address before making the repo public.

---

## Critical Findings

### 1. Hardcoded Test Credentials (LOW RISK)

**File:** `overlays/prod/seaweedfs/manifests/all.yaml:835-839`
```yaml
stringData:
  user: "YourSWUser"
  password: "HardCodedPassword"
```
**Action:** Replace with 1Password OnePasswordItem CRD reference

### 2. ClickHouse Default Credentials (LOW-MEDIUM RISK)

**File:** `overlays/cluster-critical/signoz/manifests/all.yaml:115-116, 3435`
- Username: `clickhouse_operator`
- Password: `clickhouse_operator_password`
- Admin: UUID placeholder

**Action:** Verify these are intentional defaults; consider rotating for production

---

## Personal Information to Remove/Sanitize

| Item | Files | Recommendation |
|------|-------|----------------|
| **Email** `joe@jomcgi.dev` | `charts/claude/Chart.yaml`, `values.yaml`, CV | Replace with generic or remove |
| **Name** Joe McGinley | CV, Chart.yaml, index.astro | Remove from charts, keep on personal site |
| **Full CV** | `websites/jomcgi.dev/src/assets/cv.md` | Remove or redact employment history |
| **LinkedIn** | index.astro, cv.md | Personal choice |
| **Location** Vancouver, BC | CV, index.astro | Personal choice |

### Employment History Exposed
The CV includes detailed employment at:
- BenchSci (Oct 2022 – Present)
- Ensono (May 2022 to Oct 2022)
- Hometree (Sep 2021 to May 2022)
- AXA (Jan 2021 to Sep 2021)
- Sky (Feb 2020 to Jan 2021)

---

## Infrastructure Details Exposed (Generally Safe)

These are visible but **not security risks** - more about privacy preference:

### Domain Names
- `jomcgi.dev` (primary)
- `ships.jomcgi.dev`, `argocd.jomcgi.dev`, `signoz.jomcgi.dev`, `claude.jomcgi.dev`, etc.

### 1Password Vault References
- Vault name: `k8s-homelab`
- Item paths: `vaults/k8s-homelab/items/claude.jomcgi.dev`, etc.

**Note:** These are references, not actual secrets. Knowing vault/item names doesn't grant access.

### Container Registry
- `ghcr.io/jomcgi/homelab/...` - exposes GitHub username and service names

---

## What's Properly Secured (No Action Needed)

| Secret Type | Management Method |
|-------------|-------------------|
| GitHub tokens | 1Password OnePasswordItem CRD |
| BuildBuddy API key | 1Password OnePasswordItem CRD |
| Google/Gemini API key | 1Password OnePasswordItem CRD |
| AISStream API key | 1Password OnePasswordItem CRD |
| Cloudflare tunnel creds | 1Password OnePasswordItem CRD |
| GHCR pull secrets | 1Password OnePasswordItem CRD |
| SigNoz API key | Environment variable reference |

**No private keys, SSH keys, or actual credentials found in the repository.**

---

## Recommended Actions

### Must Fix Before Public
1. [ ] Replace SeaweedFS hardcoded credentials with 1Password reference
2. [ ] Review ClickHouse default credentials

### Optional (Low Priority)
3. [ ] Replace personal email in Helm chart maintainer fields (or keep - common in open source)
4. [ ] Decide if 1Password vault name `k8s-homelab` should be genericized (knowing vault names doesn't grant access)

### No Action Needed (User Decision)
- ~~CV with employment history~~ - **Keep as-is** (personal site, intentionally public)
- Personal website content (name, LinkedIn, location) - intentionally public
- Domain `jomcgi.dev` references - this is the owner's domain

---

## Files to Review

| File | Issue |
|------|-------|
| `overlays/prod/seaweedfs/manifests/all.yaml` | Hardcoded test password |
| `overlays/cluster-critical/signoz/manifests/all.yaml` | Default ClickHouse creds |
| `websites/jomcgi.dev/src/assets/cv.md` | Full CV with employment |
| `charts/claude/Chart.yaml` | Personal email |
| `charts/claude/values.yaml` | Git email config |

---

## Conclusion

The repository is **well-architected for security**. The main concerns are:
1. One placeholder password that should be moved to 1Password
2. Personal information (name, email, CV) that's a privacy decision, not a security vulnerability

The codebase follows excellent patterns that could serve as a reference for others setting up secure homelabs.
