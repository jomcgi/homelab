# Inference Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename the llama-cpp chart to `inference` and make the backend swappable between llama.cpp and vLLM via a single `backend` value.

**Architecture:** Single Helm chart with conditional deployment logic based on `backend: llama-cpp | vllm`. Shared infra (volumes, security, probes, service) stays DRY. Backend-specific args live in separate helper templates. Consumers use OpenAI-compatible API — URL changes from `llama-cpp.llama-cpp.svc` to `inference.inference.svc`.

**Tech Stack:** Helm 3, Kustomize, ArgoCD, llama.cpp server, vLLM

---

### Task 1: Rename directory and Chart.yaml

**Files:**

- Move: `projects/agent_platform/llama_cpp/deploy/` → `projects/agent_platform/inference/deploy/`
- Modify: `projects/agent_platform/inference/deploy/Chart.yaml`

**Step 1: Move the directory**

```bash
cd /tmp/claude-worktrees/inference-chart
git mv projects/agent_platform/llama_cpp projects/agent_platform/inference
```

**Step 2: Update Chart.yaml**

In `projects/agent_platform/inference/deploy/Chart.yaml`, change:

- `name: llama-cpp` → `name: inference`
- Bump version to `2.0.0` (breaking rename)

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: rename llama-cpp chart directory to inference"
```

---

### Task 2: Rename all helper templates

**Files:**

- Modify: `projects/agent_platform/inference/deploy/templates/_helpers.tpl`

**Step 1: Rename all template definitions**

Replace every `llama-cpp.` prefix with `inference.` in the helper templates:

- `llama-cpp.name` → `inference.name`
- `llama-cpp.fullname` → `inference.fullname`
- `llama-cpp.chart` → `inference.chart`
- `llama-cpp.labels` → `inference.labels`
- `llama-cpp.selectorLabels` → `inference.selectorLabels`
- `llama-cpp.serverArgs` → `inference.llamaCppArgs`

**Step 2: Update all template references in other files**

Update every `{{ include "llama-cpp.*" }}` call in:

- `templates/deployment.yaml`
- `templates/service.yaml`
- `templates/configmap-chat-template.yaml`
- `templates/image-pull-secret.yaml`

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: rename helper templates from llama-cpp to inference"
```

---

### Task 3: Restructure values.yaml for multi-backend support

**Files:**

- Modify: `projects/agent_platform/inference/deploy/values.yaml`

**Step 1: Add backend selector and restructure**

Rewrite `values.yaml` with:

- `backend: "llama-cpp"` at top level
- `image:` section with nested `llamaCpp:` and `vllm:` sub-keys, each with `repository` and `tag`
- Move all llama.cpp-specific server config under `llamaCpp:` key (nGpuLayers, ctxSize, flashAttn, cacheTypeK, cacheTypeV, threads, jinja, mmproj, chatTemplate, extraArgs)
- Add `vllm:` key with defaults (maxModelLen: 32768, gpuMemoryUtilization: 0.95, dtype: "auto", quantization: "", tokenizer: "", extraArgs: [])
- Keep shared config at top level: `server:` (port, host), `modelVolume:`, `resources:`, `nodeSelector:`, `podAnnotations:`, `strategy:`, security contexts, probes, `imagePullSecret:`, `runtimeClassName:`

Full values.yaml content:

```yaml
backend: "llama-cpp"

image:
  llamaCpp:
    repository: ghcr.io/ggml-org/llama.cpp
    tag: server-cuda
    pullPolicy: IfNotPresent
  vllm:
    repository: vllm/vllm-openai
    tag: latest
    pullPolicy: IfNotPresent

fullnameOverride: ""

imagePullSecret:
  enabled: false

modelVolume:
  enabled: false
  reference: ""
  mountPath: "/model-image"

server:
  host: "0.0.0.0"
  port: 8080

llamaCpp:
  nGpuLayers: 99
  ctxSize: 32768
  flashAttn: "on"
  cacheTypeK: "q8_0"
  cacheTypeV: "q4_0"
  threads: 8
  jinja: true
  modelPath: ""
  mmproj: ""
  chatTemplate: ""
  extraArgs: []

vllm:
  maxModelLen: 32768
  gpuMemoryUtilization: 0.95
  dtype: "auto"
  quantization: ""
  tokenizer: ""
  extraArgs: []

runtimeClassName: nvidia

nodeSelector: {}

strategy:
  type: Recreate

podAnnotations: {}

podSecurityContext:
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL

startupProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 180

livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 15
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3

resources:
  requests:
    cpu: 4
    memory: "32Gi"
    nvidia.com/gpu: 1
  limits:
    memory: "48Gi"
    nvidia.com/gpu: 1
```

**Step 2: Commit**

```bash
git add -A
git commit -m "refactor: restructure values.yaml for multi-backend support"
```

---

### Task 4: Add vLLM args helper and update deployment template

**Files:**

- Modify: `projects/agent_platform/inference/deploy/templates/_helpers.tpl`
- Modify: `projects/agent_platform/inference/deploy/templates/deployment.yaml`

**Step 1: Add `inference.vllmArgs` helper to `_helpers.tpl`**

Add a new named template that builds vLLM CLI args:

```
{{- define "inference.vllmArgs" -}}
--host {{ .Values.server.host }} \
--port {{ .Values.server.port }} \
--max-model-len {{ .Values.vllm.maxModelLen }} \
--gpu-memory-utilization {{ .Values.vllm.gpuMemoryUtilization }} \
--dtype {{ .Values.vllm.dtype }} \
{{- if .Values.vllm.quantization }}
--quantization {{ .Values.vllm.quantization }} \
{{- end }}
{{- if .Values.vllm.tokenizer }}
--tokenizer {{ .Values.vllm.tokenizer }} \
{{- end }}
{{- range .Values.vllm.extraArgs }}
{{ . }} \
{{- end }}
{{- end }}
```

**Step 2: Update deployment.yaml for backend switching**

The deployment template needs to:

1. Select the correct image:

```yaml
{{- $backendKey := ternary "llamaCpp" "vllm" (eq .Values.backend "llama-cpp") }}
{{- $img := index .Values.image $backendKey }}
image: "{{ $img.repository }}:{{ $img.tag }}"
imagePullPolicy: {{ $img.pullPolicy }}
```

2. Conditionally render the container command:

- `{{- if eq .Values.backend "llama-cpp" }}` → existing llama.cpp auto-discovery shell script using `inference.llamaCppArgs`
- `{{- else if eq .Values.backend "vllm" }}` → vLLM command:
  ```
  MODEL=$(find /model-image -maxdepth 2 -name '*.gguf' ! -name 'mmproj*' -type f | sort | head -1)
  exec vllm serve "$MODEL" \
    {{ include "inference.vllmArgs" . | indent 4 | trim }}
  ```

3. Keep shared: ports, probes, resources, volume mounts, security context.

4. The chat-template ConfigMap volume mount should be conditional on `backend == "llama-cpp"` AND `chatTemplate` being set (vLLM doesn't use Jinja file mounts the same way).

**Step 3: Verify with helm template**

```bash
helm template test projects/agent_platform/inference/deploy/ -f projects/agent_platform/inference/deploy/values.yaml
```

Verify the rendered output uses llama-cpp image and args by default.

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: add vLLM backend support to inference chart"
```

---

### Task 5: Update values-prod.yaml

**Files:**

- Modify: `projects/agent_platform/inference/deploy/values-prod.yaml`

**Step 1: Update values-prod.yaml for new structure**

Restructure to match the new values schema. Keep `backend: "llama-cpp"` for now (we'll switch to vLLM in a follow-up after testing). Move existing llama.cpp-specific args under the `llamaCpp:` key:

```yaml
fullnameOverride: "inference"

backend: "llama-cpp"

image:
  llamaCpp:
    tag: "server-cuda-b8643"

imagePullSecret:
  enabled: true

modelVolume:
  enabled: true
  reference: "ghcr.io/jomcgi/models/qwen/qwen3.6-27b:unsloth-gguf-q4-k-m-mmproj"
  mountPath: "/model-image"

llamaCpp:
  nGpuLayers: 999
  ctxSize: 32768
  flashAttn: "on"
  cacheTypeK: "f16"
  cacheTypeV: "q8_0"
  threads: 8
  jinja: true
  extraArgs:
    - "--batch-size"
    - "2048"
    - "--ubatch-size"
    - "512"
    - "--parallel"
    - "1"
    - "--metrics"
    - "--alias"
    - "qwen3.6-27b"
    - "--reasoning-budget"
    - "2048"
    - "--spec-type"
    - "ngram-simple"
    - "--draft"
    - "8"
    - "--cache-ram"
    - "4096"

nodeSelector:
  kubernetes.io/hostname: node-4

podAnnotations:
  linkerd.io/inject: disabled
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"

resources:
  requests:
    cpu: 2
    memory: "8Gi"
    nvidia.com/gpu: 1
  limits:
    memory: "16Gi"
    nvidia.com/gpu: 1
```

**Step 2: Commit**

```bash
git add -A
git commit -m "refactor: update values-prod.yaml for new inference chart structure"
```

---

### Task 6: Update ArgoCD application and kustomization references

**Files:**

- Modify: `projects/agent_platform/inference/deploy/application.yaml` — update path to `projects/agent_platform/inference/deploy`, namespace to `inference`
- Modify: `projects/agent_platform/kustomization.yaml` — update `./llama_cpp/deploy` → `./inference/deploy`
- Modify: `projects/agent_platform/llama_cpp_embeddings/deploy/application.yaml` — update chart path to `projects/agent_platform/inference/deploy`, keep namespace as `llama-cpp` for now (or rename too)

**Step 1: Update inference application.yaml**

Change:

- `path: projects/agent_platform/llama_cpp/deploy` → `path: projects/agent_platform/inference/deploy`
- `namespace: llama-cpp` → `namespace: inference`
- Update `targetRevision` to match new chart version `2.0.0`

**Step 2: Update agent_platform kustomization.yaml**

Change:

- `- ./llama_cpp/deploy` → `- ./inference/deploy`
- `- ./llama_cpp_embeddings/deploy` → keep as-is (embeddings still lives in its own dir, just points at new chart path)

**Step 3: Update embeddings application.yaml**

Change:

- `path: projects/agent_platform/llama_cpp/deploy` → `path: projects/agent_platform/inference/deploy`
- Keep `namespace: llama-cpp` for now (can rename in follow-up) OR rename to `inference`

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update ArgoCD and kustomization references for inference chart"
```

---

### Task 7: Update consumer service URLs

**Files:**

- Modify: `projects/monolith/deploy/values.yaml` — update `llamaCppUrl` and `embeddingUrl` to use `inference` namespace
- Modify: `projects/agent_platform/deploy/values.yaml` — update `openaiBaseUrl`

**Step 1: Update monolith deploy values**

Change:

- `llamaCppUrl: "http://llama-cpp.llama-cpp.svc.cluster.local:8080"` → `"http://inference.inference.svc.cluster.local:8080"`
- `embeddingUrl: "http://llama-cpp-embeddings.llama-cpp.svc.cluster.local:8080"` → depends on whether embeddings namespace also renames

**Step 2: Update agent-platform deploy values**

Change:

- `openaiBaseUrl: "http://llama-cpp.llama-cpp.svc.cluster.local:8080"` → `"http://inference.inference.svc.cluster.local:8080"`

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: update consumer URLs from llama-cpp to inference"
```

---

### Task 8: Run format and helm template validation

**Step 1: Run format**

```bash
cd /tmp/claude-worktrees/inference-chart
format
```

This regenerates `projects/home-cluster/kustomization.yaml` to pick up the directory rename.

**Step 2: Helm template both configurations**

```bash
# Test llama-cpp backend (default)
helm template inference projects/agent_platform/inference/deploy/ \
  -f projects/agent_platform/inference/deploy/values.yaml \
  -f projects/agent_platform/inference/deploy/values-prod.yaml

# Test vllm backend
helm template inference projects/agent_platform/inference/deploy/ \
  -f projects/agent_platform/inference/deploy/values.yaml \
  --set backend=vllm \
  --set vllm.maxModelLen=32768 \
  --set vllm.tokenizer=Qwen/Qwen3.6-27B
```

Verify:

- llama-cpp renders with `ghcr.io/ggml-org/llama.cpp` image and `--n-gpu-layers` args
- vllm renders with `vllm/vllm-openai` image and `vllm serve` command
- Both have correct labels, service, probes

**Step 3: Helm template embeddings (still uses chart)**

```bash
helm template llama-cpp-embeddings projects/agent_platform/inference/deploy/ \
  -f projects/agent_platform/llama_cpp_embeddings/deploy/values.yaml
```

**Step 4: Commit any format changes**

```bash
git add -A
git commit -m "style: auto-format after inference chart rename"
```

---

### Task 9: Run CI tests

**Step 1: Run remote tests**

```bash
bb remote test //projects/agent_platform/... --config=ci
```

If there are Bazel BUILD targets referencing `llama_cpp`, they may need updating too. Check with:

```bash
grep -r 'llama_cpp' /tmp/claude-worktrees/inference-chart/projects/agent_platform/**/BUILD 2>/dev/null
```

**Step 2: Fix any failures and commit**

---

### Task 10: Create PR

```bash
git push -u origin feat/inference-chart
gh pr create --title "refactor: rename llama-cpp chart to inference with vLLM backend support" --body "..."
```

Include in PR description:

- Summary of changes
- Note that this deploys with `backend: llama-cpp` (no behavior change)
- Follow-up PR will test `backend: vllm` with Qwen 3.6
- Consumer URL updates included
