# Semgrep Rule Generation via RL-Finetuned Qwen 3.5 9B

**Date:** 2026-03-28
**Status:** Draft
**Author:** jomcgi + Claude

## Goal

Finetune Qwen 3.5 9B to generate Semgrep rules from CVE/CWE vulnerability
descriptions, starting with Python. Given a natural language description of a
vulnerability (e.g., a CVE advisory), the model produces a complete, valid
Semgrep rule YAML — including taint-mode rules with sources, sinks,
propagators, and sanitizers.

## Motivation

Writing high-quality Semgrep rules requires deep understanding of both the
vulnerability class and Semgrep's pattern language. Pro rules are expensive to
author manually. An RL-finetuned model that can reason about vulnerability
descriptions and produce working detection rules would accelerate rule
authoring significantly.

## Hardware

Single worker node in the homelab cluster:

- **GPU:** NVIDIA RTX 4090 (24GB VRAM)
- **CPU:** AMD Ryzen 5800X3D (8C/16T)
- **RAM:** 64GB DDR5

## Training Data

### Sources

| Source                                    | Python Rules | Test Fixtures                                    | Notes                         |
| ----------------------------------------- | ------------ | ------------------------------------------------ | ----------------------------- |
| Semgrep Pro rules                         | 1,032        | Internal test suite (multi-file taint scenarios) | Vendored via OCI/Bazel        |
| Community rules (`semgrep/semgrep-rules`) | 266          | Co-located `.py` files (344 rules have them)     | Public, zero overlap with Pro |
| **Total**                                 | **1,298**    | **~1,298 with validated test cases**             |                               |

OpenGrep rules were evaluated but are a near-complete fork of community rules
(263/266 overlap) — excluded to avoid duplication.

### Pro Rule Characteristics

The Pro Python corpus is dominated by taint-mode rules:

| Property                   | Count | % of 1,032 |
| -------------------------- | ----- | ---------- |
| Taint mode (`mode: taint`) | 850   | 82%        |
| Cross-file/interproc       | 780   | 76%        |
| With propagators           | 762   | 74%        |
| With sanitizers            | 774   | 75%        |
| Pattern mode (non-taint)   | 182   | 18%        |

### CWE Coverage (Top 10, Pro + Community Combined)

| CWE     | Description            | Pro | Community | Total |
| ------- | ---------------------- | --- | --------- | ----- |
| CWE-918 | SSRF                   | 278 | 5         | 283   |
| CWE-89  | SQL Injection          | 169 | 23        | 192   |
| CWE-73  | Path Traversal         | 108 | -         | 108   |
| CWE-502 | Deserialization        | 73  | 12        | 85    |
| CWE-78  | OS Command Injection   | 42  | 33        | 75    |
| CWE-327 | Weak Crypto            | 34  | 26        | 60    |
| CWE-79  | XSS                    | 11  | 30        | 41    |
| CWE-798 | Hard-coded Credentials | 38  | -         | 38    |
| CWE-94  | Code Injection         | 35  | -         | 35    |
| CWE-22  | Path Traversal         | 34  | 5         | 39    |

### Grouping Strategy

Rules are grouped by **CWE vulnerability class**, not individual rule ID. Each
group contains all related rules across Pro and community sources, their test
fixtures, and prompt variants derived from the CWE/CVE descriptions.

```
CWE-89: SQL Injection
├── pro_rules/
│   ├── python.django.security.injection.sql-injection (taint)
│   ├── python.flask.security.injection.sql-injection (taint)
│   └── python.sqlalchemy.security.sql-injection (taint)
├── community_rules/
│   └── python.lang.security.audit.sqli (pattern)
├── test_fixtures/           # From Pro internal tests + community co-located files
│   ├── core_positive/       # Canonical vulnerable patterns (must catch)
│   ├── variant_positive/    # Subtle variations (should catch)
│   ├── core_negative/       # Safe patterns (must NOT flag)
│   └── edge_negative/       # Tricky safe code (bonus)
└── prompts/
    ├── CWE-89 description (MITRE)
    ├── CVE-2024-XXXXX advisory text
    └── Rule message field variants
```

### Train/Eval Split

Time-based split using CVE publication date from NVD to prevent data
contamination from the base model's pretraining:

| Split             | CVE Window          | Purpose                                     |
| ----------------- | ------------------- | ------------------------------------------- |
| **Train**         | Pre-2025            | Safely within Qwen 3.5's pretraining window |
| **Validation**    | Jan 2025 – Dec 2025 | Grey zone — for hyperparameter tuning       |
| **Held-out eval** | 2026+               | Guaranteed unseen by base model             |

The eval tests true generalization: given a brand-new CVE in a CWE class the
model trained on, can it produce a working rule for an unseen library/pattern?

As new CVEs are published and Semgrep releases corresponding Pro rules (via the
daily update pipeline), they automatically become fresh eval examples.

## Pipeline Architecture

### Phase 0: Data Construction (CPU-only, one-time)

1. Parse all 1,298 rules — extract id, message, metadata (CWE, OWASP,
   severity), pattern YAML
2. Group rules by CWE vulnerability class
3. Map test fixtures to rule groups (core positive, variant positive, core/edge
   negative) — using Pro internal test suite and community co-located files
4. Build prompt variants from: rule `message` field, CWE description from
   MITRE, CVE advisory text from NVD
5. Apply time-based split using CVE publication dates
6. Output: `training_data.jsonl` with per-row structure:

```json
{
  "prompt": "CVE/CWE description text",
  "language": "python",
  "cwe_group": "CWE-89",
  "target_rule": "rules:\n- id: ...\n  mode: taint\n  ...",
  "test_fixtures": {
    "core_positive": ["fixtures/sqli/django_raw_query.py", ...],
    "variant_positive": ["fixtures/sqli/f_string_query.py", ...],
    "core_negative": ["fixtures/sqli/parameterized_query.py", ...],
    "edge_negative": ["fixtures/sqli/safe_dynamic_table.py", ...]
  }
}
```

### Phase 1: SFT Warmup (GPU)

- **Method:** QLoRA — 4-bit quantized Qwen 3.5 9B base + LoRA adapters
  (rank 64-128)
- **Input:** CVE/CWE description + "Python"
- **Output:** Complete Semgrep rule YAML
- **Data:** ~1,100 training examples x prompt variants ≈ 3-5K pairs
- **Epochs:** 3-5
- **VRAM estimate:** ~16-18GB (base ~5-6GB + LoRA ~1-2GB + optimizer ~2-3GB +
  activations ~4-6GB)
- **Duration:** ~2-4 hours

### Phase 2: GRPO Reinforcement Learning (GPU + CPU)

#### Generation

Model generates N=4 candidate rules per prompt (GRPO group). Sequence length
capped at ~1024 tokens (Semgrep rules are typically 30-80 lines).

VRAM is tighter during GRPO due to simultaneous generation + backward pass.
Mitigations: group size of 4 (not 8), gradient checkpointing.

#### Reward Computation

Call `semgrep-core-proprietary` directly — the OCaml binary, bypassing
pysemgrep entirely. This is the same approach used in the existing Bazel
Semgrep test pipeline (`bazel/semgrep/defs/semgrep-test.sh`).

**Invocation:**

```bash
SEMGREP_APP_TOKEN=offline \
SEMGREP_URL=http://127.0.0.1:0 \
./semgrep-core-proprietary \
  -rules candidate_rule.yaml \
  -pro_inter_file \
  -lang python \
  /path/to/test_fixtures/ \
  -json -json_nodots
```

**Key details:**

- `SEMGREP_APP_TOKEN=offline` — Pro engine checks for presence, not validity
- `SEMGREP_URL=http://127.0.0.1:0` — prevents phoning home
- `-pro_inter_file` — enables cross-file taint analysis (required for 76% of
  Pro rules)
- OSS `semgrep-core` binary must be co-located in the same directory as the
  Pro binary
- Taint mode activates automatically when the rule uses `mode: taint`

**Performance:** ~0.12s per invocation (vs ~2s through pysemgrep). At 4
candidates per prompt with fixture-batched calls:

```
Per step: 4 candidates x 0.12s = 0.48s
With 8-way CPU parallelism: ~0.06s per step
Full RL run: 1,100 prompts x 3 epochs x 0.06s ≈ 3.3 minutes total
```

Semgrep execution is not the bottleneck — GPU generation/training dominates.

#### Grouped Reward Scoring

Reward is computed per CWE rule group, not per individual test snippet:

| Component                   | Weight               | What it measures                 |
| --------------------------- | -------------------- | -------------------------------- |
| Parses successfully         | Gate (0 or continue) | Syntactic validity               |
| Catches all `core_positive` | 0.4                  | Understands the vulnerability    |
| Catches `variant_positive`  | 0.2                  | Generalizes beyond obvious cases |
| Avoids all `core_negative`  | 0.3                  | Doesn't over-match               |
| `edge_negative` handling    | 0.1                  | Precision on tricky cases        |

GRPO computes relative rewards within each group of 4 candidates — no absolute
reward model needed.

#### Estimated Duration

~6-10 hours (GPU-bound). The 5800X3D handles Semgrep execution in parallel
with no meaningful wait.

### Phase 3: Evaluation (CPU)

Run the finetuned model on held-out 2026+ CVEs. For each:

1. Generate a Semgrep rule from the CVE description
2. Execute against the corresponding test fixtures via semgrep-core
3. Measure:
   - **Parse rate** — % of generated rules that are valid YAML/Semgrep syntax
   - **Detection recall** — % of core positive fixtures caught, per CWE class
   - **False positive rate** — % of core negative fixtures incorrectly flagged
   - **Taint correctness** — for taint rules: correct source/sink/propagator
     identification

Compare against the Pro rule oracle on the same fixtures.

## Future Expansion

### Multi-Language LoRA Bank

Once the Python pipeline works end-to-end, add Go, JavaScript, and Kubernetes
as additional LoRA adapters:

- Same Qwen 3.5 9B base loaded once on the 4090
- One LoRA adapter per language (~50-100MB each)
- Hot-swap adapters at inference time
- Lightweight router selects language-specific adapter from the CVE description

Training data already exists: 113 Go rules, 316 JavaScript rules, 11
Kubernetes rules in the Pro packs.

### Use Cases

1. **Rule authoring assistant** — given a CVE/CWE description, generate a
   complete Semgrep rule (this design)
2. **Rule generation from code examples** — given vulnerable code, generate a
   detection rule (richer input format, same pipeline)
3. **Codebase auditor** — proactively suggest what rules should exist (requires
   codebase-level context)

## Key Dependencies

- Semgrep Pro license (employee access to Pro rules + internal test fixtures)
- `semgrep-core-proprietary` binary (vendored via OCI/Bazel)
- Qwen 3.5 9B base model weights
- GRPO training framework (e.g., TRL, OpenRLHF, or verl)
- NVD API access for CVE descriptions and publication dates

## Risks

| Risk                                                                   | Impact                                         | Mitigation                                                                  |
| ---------------------------------------------------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------- |
| 1,298 rules may be insufficient for SFT                                | Weak baseline before RL                        | Prompt augmentation (3-5 variants per rule), community rule augmentation    |
| GRPO on 4090 may OOM with 9B model                                     | Cannot train                                   | Reduce group size to 2-3, reduce LoRA rank, try gradient checkpointing      |
| Model generates syntactically valid but semantically wrong taint rules | Poor detection quality                         | Grouped reward with weighted scoring penalizes over-matching                |
| Pro test fixtures may not have sufficient negative examples            | Reward signal doesn't penalize false positives | Generate additional negative fixtures with LLM, validate against Pro oracle |
| Semgrep Pro license terms may restrict use for model training          | Legal blocker                                  | Verify internally — employee access may have different terms                |
