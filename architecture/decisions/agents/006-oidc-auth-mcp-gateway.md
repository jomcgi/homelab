# ADR 006: OIDC Authentication for MCP Gateway

**Author:** Joe McGinley
**Status:** Draft
**Created:** 2026-03-01
**Relates to:** [003-context-forge](003-context-forge.md), [005-role-based-mcp-access](005-role-based-mcp-access.md)

---

## Problem

The MCP gateway (Context Forge) is currently protected by Cloudflare Access service tokens — static `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers injected via `mcp-remote`. This works for Claude Code CLI but blocks browser-based MCP clients entirely:

1. **Claude.ai web chat** supports remote MCP servers via its "Add custom connector" dialog, but authenticates exclusively via OAuth 2.0. It cannot send custom CF Access headers — there is no mechanism for static credentials in the browser flow.

2. **Service tokens are shared secrets** — the same token is used by every local agent session. There is no per-user identity, no session expiry beyond the token's TTL, and no way to revoke access for a single session without rotating the token for everyone.

3. **Two auth systems** — Cloudflare Access gates the edge, Context Forge has its own auth (`AUTH_REQUIRED`, `MCP_CLIENT_AUTH_ENABLED`) but `MCP_REQUIRE_AUTH=false` because CF Access is the gatekeeper. This split makes it unclear where authentication is enforced and creates a false sense of security if either layer is misconfigured.

---

## Proposal

Replace the Cloudflare Access service token gatekeeper with Context Forge's built-in OAuth 2.0 authorization server, backed by Cloudflare Access for SaaS as the OIDC identity provider. All MCP clients — CLI and web — authenticate through the same OAuth flow.

| Aspect                 | Today                                       | Proposed                                                                         |
| ---------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- |
| **Edge auth**          | CF Access service token (static headers)    | None — CF Tunnel still routes traffic (DDoS, TLS) but Access application removed |
| **MCP endpoint auth**  | `MCP_REQUIRE_AUTH=false` (trusts CF Access) | `MCP_REQUIRE_AUTH=true` (Context Forge validates OAuth tokens)                   |
| **Identity provider**  | N/A (service token has no user identity)    | Cloudflare Access for SaaS (OIDC) — reuses existing CF Zero Trust IdP            |
| **Claude Code CLI**    | `mcp-remote` + CF service token headers     | `mcp-remote` (OAuth flow — opens browser, caches token)                          |
| **Claude.ai web**      | Not possible                                | Works via standard MCP connector dialog                                          |
| **In-cluster agents**  | ClusterIP, no auth                          | Unchanged — ClusterIP access stays unauthenticated                               |
| **Token type**         | CF Access JWT (edge-validated)              | Context Forge OAuth token (application-validated)                                |
| **Per-user identity**  | No                                          | Yes — SSO login identifies the user                                              |
| **Session revocation** | Rotate shared service token                 | Revoke individual user session                                                   |

---

## Architecture

### Auth Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  MCP Client (Claude Code CLI or Claude.ai web)                      │
│                                                                     │
│  1. GET /.well-known/oauth-authorization-server                     │
│  2. POST /oauth/register  (DCR — auto-registers client)            │
│  3. Redirect user → /oauth/authorize                                │
│        └──► CF Access SSO login (OTP / GitHub / Google)             │
│  4. Callback with auth code                                         │
│  5. POST /oauth/token  (exchange for access token)                  │
│  6. POST /mcp/  with Authorization: Bearer <token>                  │
└─────────────────────────────────────────────────────────────────────┘

         │                                    ▲
         │ HTTPS (Cloudflare Tunnel)          │ OIDC (authorization code flow)
         ▼                                    │

┌─ mcp.jomcgi.dev ───────────────────────────────────────────────────┐
│                                                                     │
│  Cloudflare Tunnel (DDoS protection, TLS termination)               │
│  NO Cloudflare Access application — tunnel route only               │
│                                                                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─ Namespace: mcp-gateway ───────────────────────────────────────────┐
│                                                                     │
│  Context Forge (OAuth Authorization Server + MCP Gateway)           │
│  ├─ OAuth discovery: /.well-known/oauth-authorization-server        │
│  ├─ DCR endpoint:    /oauth/register                                │
│  ├─ Authorization:   /oauth/authorize → CF Access OIDC login        │
│  ├─ Token exchange:  /oauth/token                                   │
│  ├─ MCP endpoint:    /mcp/ (Bearer token required)                  │
│  └─ SSO provider:    Cloudflare Access for SaaS (generic OIDC)      │
│                                                                     │
│  Backends (unchanged):                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                            │
│  │ SigNoz   │ │ ArgoCD   │ │ Longhorn │                            │
│  │ :8080    │ │ :80      │ │ :80      │                            │
│  └──────────┘ └──────────┘ └──────────┘                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### In-Cluster Access (Unchanged)

In-cluster agents (OpenHands sandboxes, Goose pods) continue to access Context Forge via ClusterIP at `http://context-forge-mcp-stack-mcpgateway.mcp-gateway.svc.cluster.local:80/mcp`. No OAuth required — ClusterIP is not externally reachable, and sandbox pods are already scoped to isolated namespaces.

### Cloudflare Access for SaaS as OIDC Provider

Cloudflare Access for SaaS acts as a standards-compliant OIDC provider, exposing:

| Endpoint      | URL                                                                                                        |
| ------------- | ---------------------------------------------------------------------------------------------------------- |
| Authorization | `https://<team>.cloudflareaccess.com/cdn-cgi/access/sso/oidc/<client-id>/authorization`                    |
| Token         | `https://<team>.cloudflareaccess.com/cdn-cgi/access/sso/oidc/<client-id>/token`                            |
| Userinfo      | `https://<team>.cloudflareaccess.com/cdn-cgi/access/sso/oidc/<client-id>/userinfo`                         |
| JWKS          | `https://<team>.cloudflareaccess.com/cdn-cgi/access/sso/oidc/<client-id>/jwks`                             |
| Discovery     | `https://<team>.cloudflareaccess.com/cdn-cgi/access/sso/oidc/<client-id>/.well-known/openid-configuration` |

This reuses whatever identity provider is already configured in CF Zero Trust (one-time PIN at minimum, optionally GitHub/Google). No new identity provider accounts needed.

---

## Implementation

### Phase 1: Cloudflare Configuration

- [ ] Create a SaaS OIDC application in Cloudflare Zero Trust (Access → Applications → SaaS)
  - Application name: `Context Forge MCP`
  - Auth protocol: OIDC
  - Redirect URL: `https://mcp.jomcgi.dev/auth/sso/callback/cloudflare`
  - Scopes: `openid`, `email`, `profile`
- [ ] Add Allow policy scoped to authorized email(s)
- [ ] Copy Client ID, Client Secret, and OIDC endpoint URLs
- [ ] Store CF OIDC Client ID and Client Secret in 1Password (`context-forge` item)
- [ ] Remove (or disable) the existing self-hosted CF Access application for `mcp.jomcgi.dev`
  - Tunnel route stays — only the Access gatekeeper is removed

### Phase 2: Context Forge Configuration

- [ ] Add SSO + OAuth environment variables to 1Password secret or values.yaml:
  - `SSO_ENABLED=true`
  - `SSO_GENERIC_ENABLED=true`
  - `SSO_GENERIC_PROVIDER_ID=cloudflare`
  - `SSO_GENERIC_DISPLAY_NAME=Cloudflare Access`
  - `SSO_GENERIC_CLIENT_ID=<from CF Zero Trust>`
  - `SSO_GENERIC_CLIENT_SECRET=<from CF Zero Trust>`
  - `SSO_GENERIC_AUTHORIZATION_URL=<CF authorization endpoint>`
  - `SSO_GENERIC_TOKEN_URL=<CF token endpoint>`
  - `SSO_GENERIC_USERINFO_URL=<CF userinfo endpoint>`
  - `SSO_GENERIC_ISSUER=<CF issuer URL>`
  - `SSO_GENERIC_SCOPE=openid profile email`
  - `SSO_AUTO_CREATE_USERS=true`
  - `SSO_TRUSTED_DOMAINS=jomcgi.dev` (controls who can _log in_ — authorization is handled by ADR 005's team/RBAC layer)
  - `SSO_PRESERVE_ADMIN_AUTH=true`
- [ ] Enable Context Forge OAuth authorization server:
  - `MCP_REQUIRE_AUTH=true`
  - `OAUTH_DISCOVERY_ENABLED=true`
- [ ] Deploy updated configuration via GitOps (values.yaml change → ArgoCD auto-sync)
- [ ] Verify OAuth discovery endpoint returns metadata: `GET https://mcp.jomcgi.dev/.well-known/oauth-authorization-server`

### Phase 3: Client Configuration

- [ ] Update `.mcp.json` — remove CF service token headers:
  ```json
  {
    "mcpServers": {
      "context-forge": {
        "type": "stdio",
        "command": "npx",
        "args": ["mcp-remote", "https://mcp.jomcgi.dev/mcp/"]
      }
    }
  }
  ```
- [ ] Test Claude Code CLI: `mcp-remote` should open browser for OAuth login, cache token
- [ ] Add connector in Claude.ai web (Settings → Integrations → Add custom connector):
  - Name: `homelab-context-forge`
  - Remote MCP server URL: `https://mcp.jomcgi.dev/mcp/`
  - OAuth Client ID / Secret: leave empty (DCR auto-registers)
- [ ] Test Claude.ai web: verify SigNoz tools are available after SSO login

### Phase 4: Cleanup

- [ ] Remove `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` from local `direnv` config
- [ ] Revoke the CF Access service token for `mcp.jomcgi.dev` in Zero Trust dashboard
- [ ] Update ADR 003 status to note OIDC auth replaces the service token model

---

## Security

### What Changes

- **Authentication moves from edge to application.** Cloudflare Tunnel still provides DDoS protection and TLS termination. The authentication decision moves from CF Access (edge) to Context Forge (application). This is the standard model for OAuth-protected APIs — the reverse proxy handles transport security, the application handles identity.

- **Per-user identity replaces shared secrets.** Each session is tied to an authenticated user via SSO. Sessions can be revoked individually. Audit logs show which user made which MCP tool call.

- **OAuth tokens are short-lived.** Context Forge issues tokens with configurable expiry (default: minutes, not days). Refresh tokens extend sessions without re-authentication. CF service tokens had static TTLs set at creation.

### What Stays the Same

- Non-root, read-only filesystem, drop all capabilities (standard security context)
- Secrets via 1Password (CF OIDC credentials added to existing `context-forge` item)
- Ingress via Cloudflare Tunnel only (no direct internet exposure)
- In-cluster access via ClusterIP (unchanged, no auth required)
- Backend credentials (SigNoz API key, ArgoCD token) remain server-side — agents never see them

### Deviations from Security Model

**One deviation:** The self-hosted CF Access application for `mcp.jomcgi.dev` is removed. Traffic from the internet to Context Forge's OAuth endpoints (discovery, authorize, token, register) is no longer gated by Cloudflare Access. This is intentional — these endpoints must be publicly reachable for the OAuth flow to work. The `/mcp` endpoint itself requires a valid Bearer token, enforced by Context Forge.

This is the same pattern used by any public OAuth-protected API (GitHub API, Slack API, etc.) — discovery and token endpoints are public, resource endpoints require authentication.

---

## Risks

| Risk                                                                | Likelihood | Impact | Mitigation                                                                                                                                                                    |
| ------------------------------------------------------------------- | ---------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **OAuth endpoint abuse** — discovery/token endpoints are now public | Medium     | Low    | Rate limiting via CF Tunnel + Context Forge built-in rate limits. DCR registration is the main vector — monitor for unusual client registrations.                             |
| **DCR spam** — automated client registrations                       | Low        | Low    | Context Forge supports `DCR_ALLOWED_ISSUERS` to restrict which authorization servers can register. Monitor registered clients via admin API.                                  |
| **Token theft** — stolen OAuth token grants MCP access              | Low        | Medium | Short token expiry (minutes). Refresh tokens tied to session. Same risk profile as any OAuth API — no worse than the current shared service token.                            |
| **SSO outage** — CF Access OIDC endpoints go down                   | Low        | Medium | Existing cached tokens continue to work until expiry. `SSO_PRESERVE_ADMIN_AUTH=true` keeps local admin access for emergency. CLI can fall back to direct admin JWT if needed. |
| **Browser popup on CLI** — `mcp-remote` OAuth opens a browser tab   | Certain    | Low    | One-time action per session. Token is cached locally. Headless environments (CI, remote SSH) may need a pre-authenticated token — address if needed.                          |

---

## Open Questions

1. **DCR vs static client credentials for Claude.ai** — Claude.ai supports both Dynamic Client Registration (auto-registers) and static credentials (entered in advanced settings). DCR is cleaner but adds a public registration endpoint. If DCR proves noisy, fall back to static client credentials.

2. **Team assignment for SSO-created users** — `SSO_AUTO_CREATE_USERS=true` creates a Context Forge user on first login, but does not assign them to a team. ADR 005's RBAC model depends on users being in specific teams (`infra-agents`, `web-chat`) with a `developer` role. The bridge between authentication (this ADR) and authorization (ADR 005) needs a team assignment mechanism. Options:
   - **SSO group claim mapping** (recommended) — CF Access for SaaS supports the `groups` scope. Map CF Access groups to Context Forge teams. This is automatic and doesn't require manual intervention after first login.
   - **Admin manual assignment** — admin assigns team after first login. Simple but doesn't scale and breaks the Claude.ai flow (user would authenticate but have no tool access until manually promoted).
   - **Default team assignment** — new SSO users auto-join a default team (e.g., `web-chat` with read-only SigNoz). CLI users are manually promoted to `infra-agents`. Safe default, but requires investigating whether Context Forge supports default team assignment on user creation.

3. **In-cluster agents and OAuth** — Currently in-cluster agents bypass auth entirely via ClusterIP. If per-agent identity becomes important (audit logs per sandbox), in-cluster agents could use Context Forge's JWT auth with service accounts. More broadly, _all_ user-to-team mapping — not just in-cluster — needs to be defined before ADR 005's role-based access works. This ADR provides the authentication layer; ADR 005 consumes it for authorization. The two should share a combined phasing plan.

4. **Token caching in `mcp-remote`** — Verify that `mcp-remote` persists OAuth tokens across Claude Code sessions to avoid repeated browser login prompts. If not, consider a local token cache wrapper.

---

## References

| Resource                                                                                                                                                          | Relevance                                                                              |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [Claude.ai remote MCP connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)                              | Claude.ai OAuth requirements (DCR, PKCE, callback URL)                                 |
| [Cloudflare Access for SaaS — Generic OIDC](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/saas-apps/generic-oidc-saas/) | CF Access as OIDC provider configuration                                               |
| [Context Forge — Generic OIDC SSO Setup](https://ibm.github.io/mcp-context-forge/manage/sso-generic-oidc-tutorial/)                                               | SSO environment variables and callback URL pattern                                     |
| [Context Forge — Dynamic Client Registration](https://ibm.github.io/mcp-context-forge/manage/dcr/)                                                                | DCR configuration for MCP clients                                                      |
| [Context Forge — OAuth 2.0 Integration](https://ibm.github.io/mcp-context-forge/manage/oauth/)                                                                    | OAuth authorization server configuration                                               |
| [ADR 003 — Context Forge](003-context-forge.md)                                                                                                                   | Current service-token auth model (being replaced)                                      |
| [ADR 005 — Role-Based MCP Access](005-role-based-mcp-access.md)                                                                                                   | Authorization layer that consumes this ADR's authentication model (team scoping, RBAC) |
| [architecture/security.md](../../security.md)                                                                                                                     | Cluster security model — one deviation documented above                                |
