# ADR 006: OIDC Authentication for MCP Gateway

**Author:** Joe McGinley
**Status:** Superseded by [011-cloudflare-managed-oauth](011-cloudflare-managed-oauth.md)
**Created:** 2026-03-01
**Updated:** 2026-03-06
**Relates to:** [003-context-forge](003-context-forge.md), [005-role-based-mcp-access](005-role-based-mcp-access.md)

---

## Problem

The MCP gateway (Context Forge) is currently protected by Cloudflare Access service tokens — static `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers injected via `mcp-remote`. This works for Claude Code CLI but blocks browser-based MCP clients entirely:

1. **Claude.ai web chat** supports remote MCP servers via its "Add custom connector" dialog, but authenticates exclusively via OAuth 2.0. It cannot send custom CF Access headers — there is no mechanism for static credentials in the browser flow.

2. **Service tokens are shared secrets** — the same token is used by every local agent session. There is no per-user identity, no session expiry beyond the token's TTL, and no way to revoke access for a single session without rotating the token for everyone.

3. **Two auth systems** — Cloudflare Access gates the edge, Context Forge has its own auth (`AUTH_REQUIRED`, `MCP_CLIENT_AUTH_ENABLED`) but `MCP_REQUIRE_AUTH=false` because CF Access is the gatekeeper. This split makes it unclear where authentication is enforced and creates a false sense of security if either layer is misconfigured.

---

## Proposal

Deploy [`obot-platform/mcp-oauth-proxy`](https://github.com/obot-platform/mcp-oauth-proxy) as an OAuth 2.1 proxy in front of Context Forge. The proxy:

1. Acts as the Authorization Server (serves RFC 9728 + RFC 8414 metadata, accepts DCR)
2. Delegates user authentication to Google OIDC
3. Issues its own JWTs to MCP clients
4. Validates those tokens and proxies requests to Context Forge with `X-Forwarded-User` header
5. Context Forge trusts the proxy via `TRUST_PROXY_AUTH=true`

### Why an OAuth Proxy Instead of Context Forge's Built-in SSO

The original plan (draft version of this ADR) used Context Forge's built-in SSO with Cloudflare Access for SaaS as the OIDC provider. This was abandoned because Claude.ai's MCP connector requires a full RFC 9728 → DCR → Authorization Code + PKCE flow that Context Forge's SSO integration doesn't fully implement — Context Forge can only validate its own JWTs signed with `JWT_SECRET_KEY`, not tokens from external Authorization Servers.

| Aspect                 | Today                                       | Proposed                                                                         |
| ---------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- |
| **Edge auth**          | CF Access service token (static headers)    | None — CF Tunnel still routes traffic (DDoS, TLS) but Access application removed |
| **MCP endpoint auth**  | `MCP_REQUIRE_AUTH=false` (trusts CF Access) | mcp-oauth-proxy validates its own JWTs; Context Forge trusts proxy headers       |
| **Identity provider**  | N/A (service token has no user identity)    | Google OIDC via mcp-oauth-proxy                                                  |
| **Claude Code CLI**    | `mcp-remote` + CF service token headers     | `mcp-remote` (OAuth flow — opens browser, caches token)                          |
| **Claude.ai web**      | Not possible                                | Works via standard MCP connector dialog (RFC 9728 discovery + DCR)               |
| **In-cluster agents**  | ClusterIP, no auth                          | Unchanged — ClusterIP access stays unauthenticated                               |
| **Token type**         | CF Access JWT (edge-validated)              | mcp-oauth-proxy JWT (proxy-validated)                                            |
| **Per-user identity**  | No                                          | Yes — Google OIDC login identifies the user                                      |
| **Session revocation** | Rotate shared service token                 | Pod restart clears SQLite state (acceptable for single user)                     |

---

## Architecture

### Auth Flow

```
Claude.ai web ("Add custom connector")
    │
    │ 1. GET /.well-known/oauth-protected-resource  → proxy returns metadata
    │ 2. POST /register                             → proxy auto-registers client (DCR)
    │ 3. GET /authorize                             → proxy redirects to Google
    │ 4. User authenticates with Google Workspace
    │ 5. POST /token                                → proxy issues its own JWT
    │ 6. POST /mcp with Bearer <proxy-jwt>
    ▼
┌─ mcp.jomcgi.dev ─────────────────────────────────────┐
│  Cloudflare Tunnel (DDoS, TLS) — no CF Access app     │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌─ Namespace: mcp-gateway ──────────────────────────────┐
│                                                        │
│  mcp-oauth-proxy (Deployment)                          │
│  ├─ Validates Bearer token (its own JWT)               │
│  ├─ Injects: X-Forwarded-User, X-Forwarded-Email       │
│  └─ Proxies to Context Forge ClusterIP                 │
│         ▼                                              │
│  Context Forge (existing)                              │
│  ├─ TRUST_PROXY_AUTH=true                              │
│  ├─ PROXY_USER_HEADER=X-Forwarded-User                │
│  ├─ MCP_CLIENT_AUTH_ENABLED=false (proxy handles auth) │
│  └─ MCP tools served to authenticated user             │
│                                                        │
│  In-cluster agents (ClusterIP) → Context Forge direct  │
│  (unchanged, no auth)                                  │
└────────────────────────────────────────────────────────┘
```

### In-Cluster Access (Unchanged)

In-cluster agents (OpenHands sandboxes, Goose pods) continue to access Context Forge via ClusterIP at `http://context-forge-mcp-stack-mcpgateway.mcp-gateway.svc.cluster.local:80/mcp`. No OAuth required — ClusterIP is not externally reachable, and sandbox pods are already scoped to isolated namespaces.

---

## Implementation

### Phase 0: Google Cloud Console (Manual)

- [x] Create OAuth Client ID in GCP Console (Web application type)
  - Authorized redirect URI: `https://mcp.jomcgi.dev/callback`
  - Scopes: `openid`, `email`, `profile`
- [x] Store Client ID, Client Secret, and ENCRYPTION_KEY in 1Password (`mcp-oauth-proxy` item)

### Phase 1: Deploy mcp-oauth-proxy

- [x] Create Helm chart at `projects/mcp/oauth-proxy/chart/` (deployment, service, onepassworditem)
- [x] Create ArgoCD application at `projects/mcp/oauth-proxy/deploy/`
- [x] Add to `projects/home-cluster/kustomization.yaml`

### Phase 2: Update Cloudflare Tunnel Route

- [x] Route `mcp.jomcgi.dev` to `http://mcp-oauth-proxy.mcp-gateway.svc.cluster.local:8080`

### Phase 3: Update Context Forge Configuration

- [x] Remove SSO config (SSO*ENABLED, SSO_GENERIC*\*, OAUTH_DISCOVERY_ENABLED, MCPGATEWAY_DCR_ENABLED)
- [x] Set `TRUST_PROXY_AUTH=true`, `PROXY_USER_HEADER=X-Forwarded-User`
- [x] Set `MCP_CLIENT_AUTH_ENABLED=false`, `MCP_REQUIRE_AUTH=false`
- [ ] Remove SSO fields from 1Password `context-forge` item (manual)

### Phase 4: Client Configuration

- [ ] Configure Claude.ai web connector: URL `https://mcp.jomcgi.dev/mcp/`
- [ ] Update Claude Code `.mcp.json` to use `mcp-remote` without CF Access headers

### Phase 5: Cleanup

- [ ] Remove `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` from local `direnv`
- [ ] Revoke CF Access service token in Zero Trust dashboard

---

## Security

### What Changes

- **Authentication moves from edge to proxy.** Cloudflare Tunnel still provides DDoS protection and TLS termination. The mcp-oauth-proxy validates its own JWTs before proxying to Context Forge. Context Forge trusts proxy headers (`TRUST_PROXY_AUTH=true`).

- **Per-user identity replaces shared secrets.** Each session is tied to an authenticated Google user. The proxy injects `X-Forwarded-User` and `X-Forwarded-Email` headers.

- **SQLite state is ephemeral.** DCR registrations are stored in SQLite on an emptyDir volume. Pod restart loses state — Claude.ai re-registers on next connection. Acceptable for single user.

### What Stays the Same

- Non-root (uid 65532), drop all capabilities
- Secrets via 1Password (Google OAuth credentials in new `mcp-oauth-proxy` item)
- Ingress via Cloudflare Tunnel only (no direct internet exposure)
- In-cluster access via ClusterIP (unchanged, no auth required)
- Backend credentials (SigNoz API key, ArgoCD token) remain server-side — agents never see them

### Deviations from Security Model

**One deviation:** The OAuth proxy's discovery, registration, and authorization endpoints are publicly reachable (no CF Access gatekeeper). This is intentional — these endpoints must be public for the OAuth flow to work. The `/mcp` endpoint requires a valid Bearer token validated by the proxy. Same pattern as any public OAuth-protected API (GitHub API, Slack API).

---

## Risks

| Risk                                               | Likelihood | Impact | Mitigation                                                                                  |
| -------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------- |
| `mcp-oauth-proxy` doesn't implement RFC 9728/DCR   | Low        | High   | Fall back to `sigbit/mcp-auth-proxy` (73 stars, Claude.ai verified, MIT)                    |
| Pod restart loses SQLite state (DCR registrations) | Certain    | Low    | Claude.ai re-registers on next connection — acceptable for single user                      |
| `TRUST_PROXY_AUTH` bypasses all MCP auth           | Low        | Medium | Proxy only reachable via Tunnel (external) or ClusterIP (internal) — same security boundary |
| Container image `latest` tag is unstable           | Medium     | Low    | Pin to specific release tag once verified                                                   |
| Google OAuth callback URL mismatch                 | Low        | Low    | Verify exact callback path from proxy docs before creating GCP OAuth client                 |
| Browser popup on CLI                               | Certain    | Low    | One-time per session. Token cached locally. Headless envs may need pre-auth token.          |

---

## Open Questions

1. **Pin container image tag** — `ghcr.io/obot-platform/mcp-oauth-proxy:latest` should be pinned to a specific release once the deployment is verified working. Check releases at https://github.com/obot-platform/mcp-oauth-proxy/releases.

2. **Team assignment for proxy-identified users** — The proxy injects `X-Forwarded-User` with the Google email, but Context Forge's RBAC model (ADR 005) depends on users being in specific teams. With `TRUST_PROXY_AUTH=true`, Context Forge auto-creates users from the header. Investigate whether default team assignment works, or if admin manual assignment is needed.

3. **Token caching in `mcp-remote`** — Verify that `mcp-remote` persists OAuth tokens across Claude Code sessions to avoid repeated browser login prompts.

---

## References

| Resource                                                                                                                             | Relevance                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| [obot-platform/mcp-oauth-proxy](https://github.com/obot-platform/mcp-oauth-proxy)                                                    | OAuth 2.1 proxy used for this implementation                |
| [Claude.ai remote MCP connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers) | Claude.ai OAuth requirements (DCR, PKCE, callback URL)      |
| [ADR 003 — Context Forge](003-context-forge.md)                                                                                      | Current service-token auth model (being replaced)           |
| [ADR 005 — Role-Based MCP Access](005-role-based-mcp-access.md)                                                                      | Authorization layer that consumes this ADR's authentication |
| [docs/security.md](../../security.md)                                                                                                | Cluster security model — one deviation documented above     |
