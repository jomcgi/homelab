# Inference Chart Design

## Problem

The `llama-cpp` Helm chart is tightly coupled to the llama.cpp server binary.
Qwen 3.6's hybrid Mamba+Attention architecture produces only 17–27 tok/s on a
4090 due to llama.cpp's immature hybrid/SSM CUDA support (34 graph splits per
token, CPU-side SSM compute). Production serving frameworks like vLLM have fused
Mamba kernels and CUDA graph capture that should unlock the expected 40–50 tok/s.

## Goal

Rename the chart from `llama-cpp` to `inference` and make the backend swappable
between llama.cpp and vLLM via a single `backend` value. Consumers (monolith
bot, agent orchestrator) use the OpenAI-compatible API and should not need to
change when the backend switches.

## Constraints

- Single GPU (RTX 4090), one backend at a time
- Same GGUF model files for both backends (OCI image volumes)
- OpenAI-compatible `/v1/chat/completions` as the common API
- Standardized health endpoint and Prometheus metrics for SigNoz
- Non-root security context, read-only root FS

## Design

### Values Structure

Shared config at top level, backend-specific config nested:

```yaml
backend: "llama-cpp" # or "vllm"

image:
  llamaCpp:
    repository: ghcr.io/ggml-org/llama.cpp
    tag: server-cuda
  vllm:
    repository: vllm/vllm-openai
    tag: latest

modelVolume:
  enabled: false
  reference: ""
  mountPath: "/model-image"

server:
  port: 8080
  host: "0.0.0.0"

llamaCpp:
  nGpuLayers: 99
  ctxSize: 32768
  flashAttn: "on"
  cacheTypeK: "q8_0"
  cacheTypeV: "q4_0"
  threads: 8
  jinja: true
  mmproj: ""
  chatTemplate: ""
  extraArgs: []

vllm:
  maxModelLen: 32768
  gpuMemoryUtilization: 0.95
  dtype: "auto"
  quantization: ""
  extraArgs: []
```

### Deployment Template

Single `deployment.yaml` with conditional logic in two places:

1. **Image selection**: `{{- $img := index .Values.image .Values.backend }}`
2. **Container command**: calls backend-specific helper (`inference.llamaCppArgs`
   or `inference.vllmArgs`) from `_helpers.tpl`

Everything else is shared: model volume, `/dev/shm`, resources, node selector,
security contexts, probes, annotations.

### Helpers

- `inference.name`, `inference.fullname`, `inference.labels`,
  `inference.selectorLabels` — renamed from `llama-cpp.*`
- `inference.llamaCppArgs` — existing `llama-cpp.serverArgs` logic
- `inference.vllmArgs` — builds `--max-model-len`, `--gpu-memory-utilization`,
  `--dtype`, etc.

### Health & Metrics

Both backends expose `/health` on the configured port. Prometheus annotations
stay the same. vLLM exposes Prometheus metrics at `/metrics` by default; llama.cpp
uses `--metrics` flag.

### Directory Structure

```
projects/agent_platform/inference/
├── deploy/
│   ├── Chart.yaml           # name: inference
│   ├── application.yaml     # ArgoCD app, namespace: inference
│   ├── kustomization.yaml
│   ├── values.yaml           # defaults (backend: llama-cpp)
│   ├── values-prod.yaml      # production overrides
│   └── templates/
│       ├── _helpers.tpl
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── configmap-chat-template.yaml
│       └── image-pull-secret.yaml
```

### Migration

- Rename directory `llama_cpp/` → `inference/`
- Update ArgoCD application to create `inference` namespace
- Update all helper template names `llama-cpp.*` → `inference.*`
- Update `home-cluster/kustomization.yaml` path reference
- Update monolith and agent-orchestrator `LLAMA_CPP_URL` env vars to point at
  `inference.inference.svc.cluster.local`
- Remove old `llama-cpp` namespace after deploy confirms healthy
