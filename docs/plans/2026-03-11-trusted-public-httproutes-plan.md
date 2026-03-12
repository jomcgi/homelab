# Trusted & Public HTTPRoute Tiers — Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a `cf-ingress` Helm library chart and migrate `todo` (public) + `todo-admin` (trusted) from static tunnel routes to Envoy Gateway HTTPRoutes with SecurityPolicy/BackendTrafficPolicy.

**Architecture:** A Helm library chart provides named templates that generate HTTPRoute + SecurityPolicy (trusted tier) or HTTPRoute + BackendTrafficPolicy (public tier). The todo_app chart depends on the library and includes two httproute templates — one per service. The cloudflare-gateway tunnel config is updated to remove the two todo static routes.

**Tech Stack:** Helm library charts, Envoy Gateway SecurityPolicy/BackendTrafficPolicy CRDs, Gateway API HTTPRoute

**Design doc:** `docs/plans/2026-03-11-trusted-public-httproutes-design.md`

---

### Task 1: Create the cf-ingress library chart skeleton

**Files:**

- Create: `projects/platform/cf-ingress-library/Chart.yaml`
- Create: `projects/platform/cf-ingress-library/templates/_httproute.tpl`
- Create: `projects/platform/cf-ingress-library/templates/_security-policy.tpl`
- Create: `projects/platform/cf-ingress-library/templates/_backend-traffic-policy.tpl`

**Step 1: Create Chart.yaml**

```yaml
# projects/platform/cf-ingress-library/Chart.yaml
apiVersion: v2
name: cf-ingress
description: Library chart for Cloudflare ingress HTTPRoute tiers (trusted/public)
type: library
version: 0.1.0
```

**Step 2: Create the HTTPRoute template**

Create `projects/platform/cf-ingress-library/templates/_httproute.tpl`:

```yaml
{{/*
cf-ingress.httproute generates an HTTPRoute with the ingress-tier label.

Usage:
  {{- include "cf-ingress.httproute" . }}

Required values under .Values.cfIngress:
  tier: "trusted" or "public"
  hostname: "app.jomcgi.dev"
  serviceName: "my-service"
  servicePort: 80
  gateway:
    name: "cloudflare-ingress"
    namespace: "envoy-gateway-system"
*/}}
{{- define "cf-ingress.httproute" -}}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ .name }}
  labels:
    ingress-tier: {{ .tier }}
spec:
  parentRefs:
    - name: {{ .gateway.name }}
      namespace: {{ .gateway.namespace }}
  hostnames:
    - {{ .hostname | quote }}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: {{ .serviceName }}
          port: {{ .servicePort }}
{{- end }}
```

**Step 3: Create the SecurityPolicy template (trusted tier)**

Create `projects/platform/cf-ingress-library/templates/_security-policy.tpl`:

```yaml
{{/*
cf-ingress.security-policy generates a SecurityPolicy for JWT validation
against Cloudflare Access.

Usage:
  {{- include "cf-ingress.security-policy" . }}

Required values:
  name: HTTPRoute name to target
  team: Cloudflare Access team name (default: "jomcgi")
*/}}
{{- define "cf-ingress.security-policy" -}}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: {{ .name }}-cf-access
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .name }}
  jwt:
    providers:
      - name: cloudflare-access
        issuer: https://{{ .team | default "jomcgi" }}.cloudflareaccess.com
        remoteJWKS:
          uri: https://{{ .team | default "jomcgi" }}.cloudflareaccess.com/cdn-cgi/access/certs
        extractFrom:
          headers:
            - name: Cf-Access-Jwt-Assertion
        claimToHeaders:
          - claim: email
            header: X-Auth-Email
{{- end }}
```

**Step 4: Create the BackendTrafficPolicy template (public tier)**

Create `projects/platform/cf-ingress-library/templates/_backend-traffic-policy.tpl`:

```yaml
{{/*
cf-ingress.rate-limit generates a BackendTrafficPolicy with rate limiting.

Usage:
  {{- include "cf-ingress.rate-limit" . }}

Required values:
  name: HTTPRoute name to target
Optional:
  rateLimit.requests: requests per unit (default: 100)
  rateLimit.unit: rate limit unit (default: "Minute")
*/}}
{{- define "cf-ingress.rate-limit" -}}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  name: {{ .name }}-rate-limit
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .name }}
  rateLimit:
    global:
      rules:
        - limit:
            requests: {{ .rateLimit.requests | default 100 }}
            unit: {{ .rateLimit.unit | default "Minute" }}
{{- end }}
```

**Step 5: Commit**

```bash
git add projects/platform/cf-ingress-library/
git commit -m "feat: add cf-ingress Helm library chart for HTTPRoute tiers"
```

---

### Task 2: Add library chart dependency to todo_app

**Files:**

- Modify: `projects/todo_app/deploy/Chart.yaml`

**Step 1: Add the cf-ingress dependency**

Add to `projects/todo_app/deploy/Chart.yaml`:

```yaml
dependencies:
  - name: cf-ingress
    version: "0.1.0"
    repository: "file://../../platform/cf-ingress-library"
```

**Step 2: Run helm dependency update**

```bash
cd projects/todo_app/deploy && helm dependency update
```

This creates/updates `Chart.lock`.

**Step 3: Commit**

```bash
git add projects/todo_app/deploy/Chart.yaml projects/todo_app/deploy/Chart.lock
git commit -m "build(todo): add cf-ingress library chart dependency"
```

---

### Task 3: Add HTTPRoute + BackendTrafficPolicy for todo (public)

**Files:**

- Create: `projects/todo_app/deploy/templates/httproute-public.yaml`
- Modify: `projects/todo_app/deploy/values.yaml` (add cfIngress config)

**Step 1: Add cfIngress values for the public service**

Add to the bottom of `projects/todo_app/deploy/values.yaml`:

```yaml
# Cloudflare ingress routing
cfIngress:
  public:
    enabled: true
    tier: public
    hostname: todo.jomcgi.dev
    serviceName: "" # set below using template
    servicePort: 80
    gateway:
      name: cloudflare-ingress
      namespace: envoy-gateway-system
    rateLimit:
      requests: 100
      unit: Minute
```

**Step 2: Create the public HTTPRoute template**

Create `projects/todo_app/deploy/templates/httproute-public.yaml`:

```yaml
{{- if .Values.cfIngress.public.enabled }}
{{- $params := dict
  "name" (printf "%s-public" (include "todo.fullname" .))
  "tier" .Values.cfIngress.public.tier
  "hostname" .Values.cfIngress.public.hostname
  "serviceName" (printf "%s-public" (include "todo.fullname" .))
  "servicePort" (.Values.cfIngress.public.servicePort | int)
  "gateway" .Values.cfIngress.public.gateway
}}
{{- include "cf-ingress.httproute" $params }}
---
{{- $rlParams := dict
  "name" (printf "%s-public" (include "todo.fullname" .))
  "rateLimit" .Values.cfIngress.public.rateLimit
}}
{{- include "cf-ingress.rate-limit" $rlParams }}
{{- end }}
```

**Step 3: Verify the template renders correctly**

```bash
helm template todo projects/todo_app/deploy/ -f projects/todo_app/deploy/values.yaml -s templates/httproute-public.yaml
```

Expected: an HTTPRoute with `ingress-tier: public` label and a BackendTrafficPolicy with rate limiting, both targeting `todo-public`.

**Step 4: Commit**

```bash
git add projects/todo_app/deploy/templates/httproute-public.yaml projects/todo_app/deploy/values.yaml
git commit -m "feat(todo): add public HTTPRoute with rate limiting via cf-ingress library"
```

---

### Task 4: Add HTTPRoute + SecurityPolicy for todo-admin (trusted)

**Files:**

- Create: `projects/todo_app/deploy/templates/httproute-admin.yaml`
- Modify: `projects/todo_app/deploy/values.yaml` (add admin cfIngress config)

**Step 1: Add cfIngress values for the admin service**

Add to `projects/todo_app/deploy/values.yaml` under the `cfIngress:` key:

```yaml
cfIngress:
  # ... existing public config ...
  admin:
    enabled: true
    tier: trusted
    hostname: todo-admin.jomcgi.dev
    serviceName: "" # set below using template
    servicePort: 8080
    gateway:
      name: cloudflare-ingress
      namespace: envoy-gateway-system
    team: jomcgi
```

**Step 2: Create the admin HTTPRoute template**

Create `projects/todo_app/deploy/templates/httproute-admin.yaml`:

```yaml
{{- if .Values.cfIngress.admin.enabled }}
{{- $params := dict
  "name" (printf "%s-admin" (include "todo.fullname" .))
  "tier" .Values.cfIngress.admin.tier
  "hostname" .Values.cfIngress.admin.hostname
  "serviceName" (printf "%s-admin" (include "todo.fullname" .))
  "servicePort" (.Values.cfIngress.admin.servicePort | int)
  "gateway" .Values.cfIngress.admin.gateway
}}
{{- include "cf-ingress.httproute" $params }}
---
{{- $spParams := dict
  "name" (printf "%s-admin" (include "todo.fullname" .))
  "team" .Values.cfIngress.admin.team
}}
{{- include "cf-ingress.security-policy" $spParams }}
{{- end }}
```

**Step 3: Verify the template renders correctly**

```bash
helm template todo projects/todo_app/deploy/ -f projects/todo_app/deploy/values.yaml -s templates/httproute-admin.yaml
```

Expected: an HTTPRoute with `ingress-tier: trusted` label and a SecurityPolicy with JWT validation targeting `todo-admin`.

**Step 4: Commit**

```bash
git add projects/todo_app/deploy/templates/httproute-admin.yaml projects/todo_app/deploy/values.yaml
git commit -m "feat(todo): add trusted HTTPRoute with JWT SecurityPolicy for admin"
```

---

### Task 5: Update cloudflare-gateway tunnel config

**Files:**

- Modify: `projects/platform/cloudflare-gateway/values-prod.yaml`

**Step 1: Remove the two todo static routes**

In `projects/platform/cloudflare-gateway/values-prod.yaml`, remove these two entries from `tunnel.ingress.routes`:

```yaml
- hostname: todo.jomcgi.dev
  service: http://todo-public.todo.svc.cluster.local:80
- hostname: todo-admin.jomcgi.dev
  service: http://todo-admin.todo.svc.cluster.local:8080
```

The remaining routes stay until those services are migrated in later phases.

**Step 2: Verify the tunnel config still renders**

```bash
helm template cloudflare-gateway projects/platform/cloudflare-gateway/ \
  -f projects/platform/cloudflare-gateway/values.yaml \
  -f projects/platform/cloudflare-gateway/values-prod.yaml \
  -s templates/tunnel-configmap.yaml
```

Expected: the configmap no longer contains `todo.jomcgi.dev` or `todo-admin.jomcgi.dev` routes. The catch-all still sends unmatched traffic to Envoy Gateway.

**Step 3: Commit**

```bash
git add projects/platform/cloudflare-gateway/values-prod.yaml
git commit -m "feat(cloudflare-gateway): remove todo static tunnel routes (now via HTTPRoute)"
```

---

### Task 6: Render full todo chart and verify

**Step 1: Render the complete chart**

```bash
helm template todo projects/todo_app/deploy/ \
  -f projects/todo_app/deploy/values.yaml \
  -f projects/todo_app/deploy/values-prod.yaml
```

Verify the output contains:

- Existing resources (Deployment, Services, PVC, etc.)
- New HTTPRoute for `todo-public` with `ingress-tier: public`
- New BackendTrafficPolicy for `todo-public` with rate limiting
- New HTTPRoute for `todo-admin` with `ingress-tier: trusted`
- New SecurityPolicy for `todo-admin` with JWT validation

**Step 2: Run format**

```bash
format
```

**Step 3: Final commit if format changed anything**

```bash
git add -A && git commit -m "style: format"
```

---

### Task 7: Push and create PR

**Step 1: Push the branch**

```bash
git push -u origin feat/trusted-public-httproutes
```

**Step 2: Create the PR**

```bash
gh pr create --title "feat: add trusted/public HTTPRoute tiers with cf-ingress library" --body "$(cat <<'EOF'
## Summary
- Adds `cf-ingress` Helm library chart providing HTTPRoute templates for two tiers:
  - **trusted**: HTTPRoute + SecurityPolicy (JWT validation against Cloudflare Access)
  - **public**: HTTPRoute + BackendTrafficPolicy (rate limiting)
- Migrates `todo` (public) and `todo-admin` (trusted) from static tunnel routes to Envoy Gateway HTTPRoutes
- Removes the two todo entries from cloudflare-gateway tunnel config

## Test plan
- [ ] `helm template` renders HTTPRoutes with correct `ingress-tier` labels
- [ ] SecurityPolicy targets todo-admin HTTPRoute with correct JWKS URI
- [ ] BackendTrafficPolicy targets todo-public HTTPRoute with rate limiting
- [ ] Tunnel configmap no longer contains todo routes
- [ ] After merge: verify todo.jomcgi.dev and todo-admin.jomcgi.dev are accessible through Envoy Gateway
- [ ] After merge: verify todo-admin.jomcgi.dev rejects requests without valid Cf-Access-Jwt-Assertion

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
