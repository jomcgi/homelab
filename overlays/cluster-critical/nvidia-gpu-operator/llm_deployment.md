# LLM Inference Framework Comparison for RTX 4090 Homelab

Your RTX 4090 (24GB VRAM) with 64GB RAM can run 20-32B parameter models effectively using any of these frameworks with appropriate quantization. **For your specific requirements—Helm deployment, function calling, and single-GPU efficiency—Ollama and vLLM emerge as the strongest candidates**, with different tradeoffs between simplicity and performance.

## Framework comparison at a glance

| Criterion | llama.cpp | vLLM | Ollama | SGLang |
|-----------|-----------|------|--------|--------|
| **Performance (30B Q4)** | 195 t/s (MoE) | 34-60 t/s | 195 t/s (MoE) | 100-195 t/s |
| **Helm Chart** | ❌ None | ✅ Official | ✅ Community | ❌ None |
| **Function Calling** | ✅ Model-dependent | ✅ Native | ✅ Native (July 2024) | ✅ Excellent |
| **Deployment Ease** | ⚠️ DIY Required | ✅ Good | ✅ Excellent | ⚠️ Manual setup |
| **Development Activity** | 🔥 Daily commits | 🔥 Very active | 🔥 Very active | 🔥 Rapid velocity |
| **Homelab Focus** | ⚠️ General purpose | Production-first | ✅ Purpose-built | Enterprise-first |
| **32B Model Fit** | ✅ Q4_K_M (~19GB) | ✅ AWQ (~18GB) | ✅ Q4_K_M (~19GB) | ✅ AWQ (~20GB) |
| **OpenAI API** | ✅ Full | ✅ Full | ✅ Full | ✅ Full |

## Performance and throughput on RTX 4090

### Benchmark results for 20-32B models

**30B MoE models** (Q4_K quantization, optimal for 24GB VRAM):
- **llama.cpp/Ollama**: 195 t/s at 4K context, 75 t/s at 57K context
- **vLLM**: Comparable single-user performance, excels with concurrent requests
- **SGLang**: 100-195 t/s with 1.5-2.3× throughput advantage in multi-turn scenarios

**32B dense models** (Q4_K quantization, near VRAM limit):
- **llama.cpp/Ollama**: 33-39 t/s generation, limited to 16K context
- **vLLM**: ~34 t/s for Qwen-32B
- **SGLang**: 85% throughput of larger models with better memory efficiency

**Prompt processing speeds**: All frameworks achieve 1,685-2,500 t/s for processing input tokens, making them highly responsive for interactive use.

### PagedAttention and RadixAttention advantages

**vLLM's PagedAttention** reduces memory waste from 60-80% down to less than 4%, enabling 2-4× higher throughput than traditional serving when handling multiple concurrent users. For your personal API server scenario (5-10 concurrent users), this translates to better responsiveness under load.

**SGLang's RadixAttention** provides 3-5× cache hit rate improvements for multi-turn conversations. If you're using the API for coding assistants with repeated context (repository information, system prompts), SGLang shows approximately 10% performance gains over vLLM through automatic prefix caching.

### The 24GB VRAM sweet spot

Your RTX 4090 is excellently positioned for this workload:
- **30B MoE models**: Optimal choice at 16.47 GB VRAM usage, delivering 195 t/s
- **32B dense models**: Functional at 18-20 GB with limited context (8-16K tokens)
- **Context tradeoff**: Larger context windows require more VRAM (32K context adds ~14GB)

All frameworks recommend Q4_K_M quantization as the ideal balance, with Q5_K_M available if you have VRAM headroom for slightly better quality.

## Memory efficiency and quantization

### Quantization support comparison

**GGUF format** (llama.cpp, Ollama):
- Q4_K_M: 4.5 bits/weight average, excellent quality/size balance
- Q5_K_M: 5.5 bits/weight, near-original quality
- Q8_0: 8-bit for maximum quality (may not fit 32B models)
- Supports 1.5-bit through 8-bit quantization range

**Advanced quantization** (vLLM, SGLang):
- **AWQ (Activation-aware Weight Quantization)**: Recommended for RTX 4090, hardware-accelerated with Marlin kernels
- **GPTQ**: Wide model availability, good speed/accuracy balance
- **FP8**: Native support on Ada architecture, enables KV cache quantization
- **bitsandbytes**: In-flight quantization without calibration

### Memory optimization strategies

**Ollama's automatic management** stands out for homelab use:
- Models automatically unload after idle timeout (default 5 minutes)
- KV cache quantization (Q8_0 halves VRAM usage, Q4_0 reduces to one-third)
- Flash Attention support via environment variable

**vLLM's memory configuration**:
```bash
--gpu-memory-utilization 0.95  # Use 95% of VRAM
--max-model-len 8192           # Limit context for larger models
--kv-cache-dtype fp8           # FP8 KV cache saves memory
--quantization awq             # For pre-quantized models
```

**Practical memory limits**: For 32B models with Q4 quantization, expect to use 18-20GB VRAM at 4-8K context, leaving minimal headroom. Consider 20-25B models if you need extended context (32K+ tokens).

## Function calling capabilities

All four frameworks now support function calling, but with varying maturity levels:

### Native OpenAI-compatible support

**vLLM** (Production-ready since v0.8.3):
- Native function calling with OpenAI-compatible API
- Tool parsers for Llama 3.1+, Mistral, Hermes, Granite models
- `tool_choice` options: auto, required, none, or named functions
- Streaming tool calls supported

**Ollama** (Added July 2024):
- Full OpenAI function calling compatibility via `/v1` endpoint
- Works with official OpenAI Python client
- Supports multiple tools per request with streaming
- Native integration with popular frameworks (LangChain, LlamaIndex)

**SGLang** (Most advanced):
- Comprehensive function calling with compressed FSM for 3× faster JSON decoding
- Structured output with regex, JSON schemas, EBNF grammars
- Separate reasoning content from final output
- Limitation: Cannot combine tool calling + structured response in single request (feature request open)

**llama.cpp** (Model-dependent):
- Requires models specifically fine-tuned for function calling (Hermes-2-Pro, Mistral 7B Instruct v0.3, Llama 3.1+)
- OpenAI-compatible via llama-server and llama-cpp-python
- Manual function execution (no automatic triggering)
- Works well but less polished than dedicated serving frameworks

### Recommended models for function calling

All frameworks support these function-calling models on RTX 4090:
- **Qwen 2.5-Coder-32B-Instruct** (AWQ 4-bit, ~18GB): Best for coding tasks
- **Llama 3.1-70B-Instruct** (Q4, aggressive optimization needed): Powerful but VRAM-constrained
- **Mistral/Mixtral series**: Good general-purpose with tool support
- **Hermes models**: Specifically fine-tuned for function calling

## Kubernetes deployment and Helm support

This is where the frameworks diverge most significantly for your homelab requirements.

### Official Helm chart availability

**vLLM** ⭐⭐⭐⭐⭐:
- Official production stack Helm chart released January 2025
- Installation: `helm repo add vllm https://vllm-project.github.io/production-stack`
- Includes request router, load balancing, Prometheus/Grafana observability
- KV cache offloading and model-aware routing
- Zero-code scaling from single to distributed deployment

**Ollama** ⭐⭐⭐⭐:
- Mature community Helm chart (otwld/ollama-helm)
- Single command installation with GPU auto-detection
- Built-in model pulling at startup
- Persistent volume management
- Ingress support for external access

**llama.cpp** ⭐⭐:
- No official Helm chart (GitHub issue #6546 tracking community interest)
- Requires DIY deployment with custom Docker images
- Community fork exists but not actively maintained
- Best deployed via Docker Compose or systemd for single-node homelab

**SGLang** ⭐⭐:
- No standalone Helm chart available
- Integration via NVIDIA NIM Helm charts (wrapper approach)
- Kubernetes CRDs available through NVIDIA Dynamo framework
- Requires manual configuration for homelab scale

### Deployment complexity assessment

**Ollama deployment** (Simplest):
```yaml
# Single command with all features
helm install ollama otwld/ollama \
  --set ollama.gpu.enabled=true \
  --set ollama.gpu.number=1 \
  --set ollama.models.pull={qwen2.5:32b-instruct-q4_K_M}
```

**vLLM deployment** (Production-ready):
```yaml
# Professional-grade with observability
helm install vllm vllm/vllm-stack -f values.yaml
# Includes metrics, routing, health checks out of box
```

**llama.cpp/SGLang** (Manual):
Both require creating custom Deployment/StatefulSet manifests, configuring GPU resources, setting up persistent volumes, and implementing service exposure—manageable but time-consuming for homelab scenarios.

### Prerequisites for all frameworks

Your K8s node will need:
- NVIDIA GPU Operator for scheduling
- Shared memory configuration (16Gi recommended)
- Persistent volume claim for model storage (100GB+)
- GPU device plugin for resource management

## Development activity and maturity

All four frameworks show exceptional development velocity as of late 2024/early 2025:

**llama.cpp**: 88,700+ stars, daily builds, multiple releases per day during active development. Extremely mature codebase with comprehensive platform support.

**vLLM**: 10,900 forks, 15+ full-time contributors across 6+ organizations. Recently joined PyTorch Foundation (May 2025). v0.11.0 released January 2025 with 1.7× V1 speedup.

**Ollama**: 155,000+ stars (most popular), 380+ contributors, bi-weekly to monthly releases. Purpose-built for personal/homelab use with massive community adoption.

**SGLang**: 19,000 stars (newest but rapid growth), 798 contributors, production-validated at massive scale (300,000+ GPUs, trillions of tokens daily). Aggressive feature development velocity.

### Recent feature additions

**Q4 2024 - Q1 2025 highlights**:
- vLLM: V1 architecture GA, PyTorch 2.8 support, NVFP4 quantization
- Ollama: Function calling (July 2024), KV cache quantization (December 2024)
- SGLang: FlashAttention3 default, Blackwell support, prefill-decode disaggregation
- llama.cpp: Multimodal support, continuous CUDA optimizations

All frameworks actively support latest models (Llama 4, Qwen 3, DeepSeek-R1) with day-one or week-one availability.

## Single-GPU homelab advantages and limitations

### Why RTX 4090 works well for this use case

**Cost efficiency**: At $1,600-2,000, the RTX 4090 delivers exceptional value compared to datacenter GPUs (A100/H100 at $10,000-40,000). Your electricity cost runs $50-100/month including overhead, breaking even versus cloud APIs in approximately 5.5 years for typical usage patterns.

**Performance sweet spot**: Consumer Ada architecture provides 450W TDP with 1,000 GB/s memory bandwidth—sufficient for 20-32B models at high throughput. You'll achieve 85% of H100 performance for single-user workloads at 100× lower cost per token.

**Privacy and control**: All inference runs locally with zero data sent to external services, ideal for proprietary code and sensitive information.

### Framework-specific homelab fit

**Ollama** is purpose-built for homelab deployment:
- Zero-configuration GPU detection
- Automatic model management and unloading
- Single-binary installation across platforms
- Strong Reddit r/selfhosted community: "Ollama + Open WebUI is the perfect self-hosted ChatGPT alternative"

**vLLM** targets production but scales down well:
- Optimized for high concurrency (50+ simultaneous requests possible)
- Professional observability and monitoring
- May be overkill for personal use but grows with your needs

**llama.cpp** offers maximum flexibility:
- Minimal dependencies, highest performance per watt
- Best for power users comfortable with command-line configuration
- Works everywhere (CPU, NVIDIA, AMD, Apple Silicon)

**SGLang** appeals to performance enthusiasts:
- Best-in-class throughput for multi-turn conversations
- Excellent for coding assistants with repository context
- Requires technical comfort with Python and troubleshooting

### Limitations to consider

**24GB VRAM ceiling**: Your RTX 4090 limits you to approximately 32B Q4 models with restricted context. 70B models require aggressive quantization (2-3 bit) with noticeable quality loss, or multi-GPU setups.

**Context tradeoffs**: At 32B model size, you're limited to 8-16K context windows. For extended context (32K+), consider 20-25B models instead.

**Single-user optimization**: All frameworks perform excellently for 1-5 concurrent users. If you need to serve 50+ simultaneous users, consider multi-GPU hardware or cloud deployment.

## Specific recommendations for your setup

### Best overall: Ollama

**Choose Ollama if**: You prioritize simple Kubernetes deployment, want a solution that "just works," and value homelab-specific design.

**Why Ollama wins for your requirements**:
1. **Helm chart excellence**: Mature community chart with one-command deployment including GPU configuration, model management, and persistence
2. **Function calling**: Production-ready since July 2024 with full OpenAI compatibility
3. **Performance**: Matches llama.cpp (both use same GGUF backend) at 195 t/s for 30B MoE models
4. **Ease of use**: Automatic model downloading, GPU detection, memory management—designed for personal servers
5. **Community support**: 155,000+ GitHub stars, extensive homelab ecosystem integration

**Deployment example**:
```bash
helm repo add otwld https://helm.otwld.com/
helm install ollama otwld/ollama -n ollama --create-namespace \
  --set ollama.gpu.enabled=true \
  --set ollama.gpu.number=1 \
  --set ollama.models.pull={qwen2.5:32b-instruct-q4_K_M} \
  --set persistentVolume.enabled=true \
  --set persistentVolume.size=100Gi
```

**Expected performance**: Qwen-32B at 33-38 t/s, 30B MoE at 195 t/s (4K context), prompt processing at 1,700+ t/s.

### Best for production-grade: vLLM

**Choose vLLM if**: You want maximum performance for concurrent users, plan to scale beyond personal use, or need enterprise-grade observability.

**Why vLLM excels**:
1. **Official Helm chart**: Production-stack with monitoring, routing, and load balancing
2. **Concurrency**: PagedAttention enables 2-4× throughput with multiple simultaneous users
3. **Quantization**: Excellent AWQ/GPTQ support with Marlin kernels for RTX 4090
4. **Maturity**: Most battle-tested production deployment, PyTorch Foundation project
5. **Function calling**: Native support since v0.8.3 with comprehensive tool parsers

**Deployment complexity**: Higher than Ollama but manageable. Requires values.yaml configuration but provides professional-grade features.

**Best use case**: If you're building an internal API for your team (5-10 developers) rather than purely personal use, vLLM's concurrency advantages justify the setup complexity.

### Best for raw performance: SGLang

**Choose SGLang if**: You're technically proficient, prioritize absolute best throughput, and frequently use multi-turn conversations or structured outputs.

**Why SGLang leads in performance**:
1. **Speed**: 1.5-2.3× faster than vLLM in multi-turn scenarios
2. **Structured generation**: 3× faster JSON decoding with compressed FSM
3. **Cache efficiency**: RadixAttention provides 10% boost with context reuse
4. **Latest models**: Day-one support for cutting-edge releases (DeepSeek-R1, Qwen 3)

**Major limitation**: No standalone Helm chart. Requires manual Kubernetes deployment or NVIDIA NIM wrapper approach. Deployment complexity significantly higher than vLLM/Ollama.

**Recommendation**: Wait 6-12 months for Kubernetes ecosystem to mature, or use now if you're comfortable with DIY deployment manifests.

### Consider llama.cpp for: Maximum flexibility

**Choose llama.cpp if**: You want direct control over every parameter, need cross-platform compatibility, or plan frequent experimentation.

**Advantages**: Minimal dependencies, works on any hardware, extremely active development, highest performance per watt.

**Major drawback**: No Helm chart means Docker Compose or systemd deployment on bare metal—works perfectly but defeats your Kubernetes preference.

**Workaround**: Deploy Ollama (which wraps llama.cpp) to get Kubernetes benefits while using the same underlying engine.

## Configuration recommendations

### Recommended model choices

**For 24GB VRAM with strong function calling**:
1. **Qwen 2.5-Coder-32B-Instruct** (AWQ 4-bit): Best coding assistant, ~18GB VRAM
2. **DeepSeek-R1-Distill-Qwen-32B**: Strong reasoning, fits with FP8
3. **Llama 3.1-70B-Instruct** (Q4): Maximum capability but limited context (8K max)
4. **Mixtral-8×22B** (Q4): MoE efficiency with only ~2 experts active per token

### Optimal Kubernetes configuration

**Ollama on single K8s node**:
```yaml
ollama:
  gpu:
    enabled: true
    type: 'nvidia'
    number: 1
  models:
    pull:
      - qwen2.5:32b-instruct-q4_K_M
    create:
      - name: qwen32b-extended
        template: |
          FROM qwen2.5:32b-instruct-q4_K_M
          PARAMETER num_ctx 16384
          PARAMETER temperature 0.7
    run:
      - qwen32b-extended
  extraEnv:
    - name: OLLAMA_KEEP_ALIVE
      value: "1h"
    - name: OLLAMA_KV_CACHE_TYPE
      value: "q8_0"
    - name: OLLAMA_FLASH_ATTENTION
      value: "1"
    - name: OLLAMA_NUM_PARALLEL
      value: "2"

resources:
  limits:
    nvidia.com/gpu: 1
    memory: 32Gi
  requests:
    nvidia.com/gpu: 1
    memory: 16Gi

persistentVolume:
  enabled: true
  size: 100Gi

ingress:
  enabled: true
  hosts:
    - host: ollama.yourhomelab.local
```

**Front-end integration**:
- Deploy Open WebUI via Helm for ChatGPT-like interface
- Connect n8n for workflow automation
- Use Continue.dev or Cursor with Ollama backend for coding

### Performance tuning tips

**Environment variables** (applicable to most frameworks):
- `OLLAMA_NUM_PARALLEL=2`: Allow 2 concurrent requests
- `OLLAMA_KV_CACHE_TYPE=q8_0`: Halve KV cache VRAM usage
- `OLLAMA_FLASH_ATTENTION=1`: Enable flash attention
- `--gpu-memory-utilization 0.95`: Use 95% of available VRAM (vLLM)

**Expected performance metrics**:
- 30B MoE models: 100-195 tokens/second generation
- 32B dense models: 33-40 tokens/second generation
- Prompt processing: 1,700-2,500 tokens/second
- Response latency: Under 1 second for typical queries
- Concurrent users: 2-5 simultaneously without degradation

## Final verdict

**For your specific requirements—Helm deployment, function calling, single RTX 4090, and homelab use—Ollama is the clear winner.** It provides the best balance of performance, deployment simplicity, and homelab-specific design. The mature Helm chart satisfies your Kubernetes requirement without compromise, while function calling support (added July 2024) meets your API needs.

**Choose Ollama** for immediate deployment with minimal friction. You'll have a production-ready API server running in under 10 minutes with one Helm command.

**Upgrade to vLLM** later if you need better concurrency for team usage (5-10 developers). Its PagedAttention advantages become significant with multiple simultaneous users, and the official Helm chart makes migration straightforward.

**Consider SGLang** in 6-12 months once Kubernetes deployment matures. The performance advantages (1.5-2.3× faster in some scenarios) are compelling, but the lack of standalone Helm chart creates unnecessary friction for homelab deployment today.

**Avoid llama.cpp** for now unless you're willing to skip Kubernetes entirely. It's an excellent framework but the missing Helm chart makes it incompatible with your stated preference for K8s deployment. Since Ollama wraps llama.cpp underneath, you get the same performance benefits with better deployment tooling.

Your RTX 4090 with 24GB VRAM is excellently positioned for this workload, capable of running 30B models at 195 tokens/second or 32B models at 34-40 tokens/second—both far exceeding the responsiveness needed for interactive coding assistants and chat interfaces.