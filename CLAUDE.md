# CLAUDE.md - Secure Kubernetes Homelab

## Project Philosophy

This repository embodies the principles from **"A Philosophy of Software Design"** by John Ousterhout:

> **Complexity is the silent killer of engineering velocity and reliability.**

Every decision in this codebase prioritizes:
- **Simplicity over cleverness**
- **Security by default**
- **Observable, testable systems**
- **Deep modules with clean interfaces**

## Architecture Overview

This is a **security-first Kubernetes homelab** running on Talos Linux, designed for:
- **Zero direct internet exposure** - All ingress via Cloudflare Tunnel
- **Meaningful integration testing** - We test actual deployments, not mocks
- **Operational simplicity** - If it's hard to operate, it's wrong

### Core Infrastructure

```
┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
│ Cloudflare      │    │ Talos Kubernetes  │    │ Observability   │
│ Tunnel          │───▶│ Cluster           │───▶│ (Grafana Cloud) │
│ (Zero Trust)    │    │ - Service A       │    │ - Metrics       │
└─────────────────┘    │ - Service B       │    │ - Logs          │
                       └───────────────────┘    │ - Traces        │
                                                └─────────────────┘
```

## Directory Structure

```
cluster/
├── crd/                    # Custom Resource Definitions
│   ├── external-secrets/   # Secrets management
│   └── longhorn/          # Persistent storage
└── services/              # Application deployments
    ├── cloudflare-tunnel/ # Secure ingress
    ├── grafana-cloud/     # Observability
    ├── obsidian/          # Note-taking
    ├── open-webui/        # AI chat interface
    └── otel-collector/    # Telemetry collection

projects/                  # Side projects
└── find_good_hikes/      # Weather + walking route finder
```

## Security Model

### Network Security
- **No direct internet exposure** - All traffic via Cloudflare Tunnel
- **Least privilege** - Services run as non-root with read-only filesystems
- **Network policies** - Microsegmentation where needed
- **Secret management** - External Secrets Operator with proper RBAC

### Container Security
Every container follows these principles:
```yaml
securityContext:
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
```

## Deployment Strategy

### GitOps with Skaffold
- **Declarative deployments** via Helm + Kustomize
- **Automated CI/CD** with GitHub Actions
- **Health checks** and **readiness probes** on everything
- **Resource limits** prevent resource exhaustion

### Testing Philosophy
We test **actual behavior**, not implementation details:

✅ **Good Tests:**
- Deploy the actual service to a test cluster
- Verify the service responds correctly via HTTP
- Confirm metrics are exported and observable
- Test the complete user journey

❌ **Bad Tests:**
- Unit tests that mock everything
- Tests that verify internal implementation
- Tests that don't exercise real deployment paths

## Key Services

### Cloudflare Tunnel
- **Zero Trust ingress** - No open firewall ports
- **Automatic HTTPS** with Cloudflare certificates
- **DDoS protection** and **WAF** built-in

### Open WebUI
- **Local AI interface** with Google Gemini integration
- **No authentication** (secured by Cloudflare Access)
- **Persistent storage** via Longhorn

### Observability Stack
- **Metrics, logs, traces** sent to Grafana Cloud
- **OpenTelemetry Collector** for telemetry aggregation
- **Prometheus-compatible** metrics from all services

## Design Principles

### 1. Deep Modules
Services have **simple interfaces** that hide **complex implementations**:
- Cloudflare Tunnel: Simple config → Complex networking
- External Secrets: Simple CRD → Complex secret synchronization
- Longhorn: Simple PVC → Complex distributed storage

### 2. Obvious Code
- **Descriptive names** over clever abbreviations
- **Clear configuration** over implicit behavior
- **Explicit dependencies** in manifests

### 3. Error Handling
We **define errors out of existence** where possible:
- Idempotent deployments (apply the same config multiple times safely)
- Graceful degradation (services work without optional dependencies)
- Automatic retries with exponential backoff

## Common Tasks

### Adding a New Service
1. Create namespace and basic manifests in `cluster/services/<name>/`
2. Add Skaffold configuration for deployment
3. Update GitHub Actions workflow for CI/CD
4. Add health checks and observability
5. Test the complete deployment path

### Security Review Checklist
- [ ] Service runs as non-root user
- [ ] Read-only root filesystem
- [ ] No privilege escalation
- [ ] Resource limits defined
- [ ] Network policies applied (if needed)
- [ ] Secrets properly managed
- [ ] Ingress via Cloudflare Tunnel only

### Observability Requirements
Every service must:
- [ ] Export Prometheus metrics on `/metrics`
- [ ] Provide health check endpoint
- [ ] Send structured logs
- [ ] Include OpenTelemetry tracing (for user-facing services)

## Development Workflow

1. **Make changes** in feature branch
2. **Test locally** with Skaffold: `skaffold dev`
3. **Verify deployment** works end-to-end
4. **Check observability** - metrics, logs, traces
5. **Create PR** - GitHub Actions runs integration tests
6. **Merge** - Automatic deployment to production

## Anti-Patterns to Avoid

### Complexity Sources
- **Cargo-culting** Kubernetes best practices without understanding why
- **Over-engineering** simple services
- **Premature optimization** before measuring
- **Magic configuration** that's hard to understand

### Security Anti-Patterns
- **Default passwords** or weak secrets
- **Running as root** unnecessarily
- **Overprivileged** service accounts
- **Direct internet exposure** bypassing Cloudflare

## Why This Design Works

This architecture prioritizes **operational simplicity**:
- **Fewer moving parts** = fewer failure modes
- **Clear interfaces** = easier troubleshooting
- **Secure by default** = less security debt
- **Observable everything** = faster incident resolution

The result is a homelab that's **easy to operate**, **secure by design**, and **simple to extend** with new services.

---

*"The best software is software that just works, without you having to think about it."*

### [Why Does Everything Feel a Bit Broken?](https://www.youtube.com/watch?v=vw2XffPmlYo&t=20s)

Most software isn't failing because of one catastrophic bug. It's degrading under the weight of a thousand tiny, thoughtless decisions. The central theme of this talk is that we've become so focused on applying rigid rules, patterns, and "best practices" that we've forgotten the most important thing: **communicating intent**.

Organizing code by architectural type (`/controllers`, `/models`, `/services`) is like smashing up a classic car and sorting the parts into bins labeled "Wheels," "Seats," and "Windshield Wipers." 
You've organized the pieces, but you've completely lost the "car-ness." The *intent* of the system is gone.

This talk was a plea to put design back into software by making every choice—from a folder name to a line of whitespace—an intentional act of communication.

![[Pasted image 20250615115211.png]]
### Intentional Design

1.  **Software is Literature:** The primary audience for your code is the next developer, not the compiler. Software is a constrained form of literature that communicates concepts from one programmer to another, which also happens to be executable by a machine. If the human-to-human communication fails, the system is brittle and hard to maintain.

2.  **Intentionality > Cleanliness:** The dogma of "Clean Code" can be actively harmful. Applying rules without understanding their purpose often leads to *more* complexity, not less. A function isn't bad because it's "too long"; it's bad if its intent is unclear. Don't just follow rules; understand the trade-offs.

![[Pasted image 20250615115253.png]]

3.  **Fight Complexity, Not Symptoms:** The enemy is complexity. [[A Philosophy of Software Design - John Ousterhout]] describes complexity as anything related to the structure of a system that makes it hard to understand or modify. The central challenge of software design is ensuring the solution's complexity is, at most, as complex as the problem it solves—and no greater.

4.  **Deep vs. Shallow Modules:** The best abstractions are **deep modules**. They hide a large amount of functionality and complexity behind a very simple interface.
    *   **Deep (Good):** A simple `File.Open()` call that hides the immense complexity of file systems, hardware drivers, and OS-level operations.
    *   **Shallow (Bad):** An abstraction that doesn't hide much. The interface is almost as complex as the implementation, adding cognitive load for no benefit. This is the "pass-through method" problem.

### Actionable Tests for Your Designs

Instead of rigid rules, ask these questions about your code and systems. They serve as tests for the quality of your design.

1.  **Could this be done with fewer moving parts?** Every dependency, module, or system you add increases cognitive load and maintenance cost. Is the trade-off worth it? Often, a few dozen lines of self-contained code are less risky than a "free" package with a huge dependency tree and an unstable future.

2.  **Is this operable?** Software that is hard to observe, deploy, manage, and automate slows the pace of change for everyone. This is a direct tax on innovation and safety. An elegant design that is impossible to run in production is a failed design.

3.  **Is it easy to change?** The best software is the software that is easy to change. Since software lives for years, its ability to adapt is its most important quality.

4.  **Does the form reflect the function?** At a micro-level, use visual cues (whitespace, code flow, naming) to guide the reader. Code with good "form" feels like poetry—it leads the eye and makes its rhythm and intent obvious. Poorly-formed code is a wall of text that forces the reader to parse every character, increasing the chance of misunderstanding.

### An End to Absolutism

> "Any design, when stretched to it's logical, absolute, extreme, becomes nonsense."

There are no silver bullets. The answer to almost every hard design question is "it depends." Our job as engineers is to understand the context, weigh the trade-offs, and make an *intentional* choice that reduces complexity and clearly communicates our intent to the next person.


### The Core Problem: Complexity

Complexity is the silent killer of engineering velocity and reliability. It's not a feature; it's a drag on everything we do—making systems brittle, hard to reason about, and a source of on-call pain. It stems from two things:
*   **Dependencies:** Modules are tangled together. A change in one place breaks another.
*   **Obscurity:** It's impossible to understand what a piece of code does without a deep-dive.

This book targets these problems head-on. Here are the key pain points it identifies:

*   **The "Tactical Tornado":** The engineer who pumps out features at lightning speed but leaves a trail of tech debt and confusion. They win the sprint but make the marathon impossible for everyone else.
*   **The "First Idea" Trap:** Even for senior engineers, the first solution to a complex problem is rarely the best. Shipping the first idea without exploring alternatives leads to brittle, hard-to-change systems.
*   **Cargo-Culting "Best Practices":** Applying rules (like "all methods must be short") without understanding the *why*. This can accidentally *increase* complexity by creating a maze of tiny, interconnected modules.

### Key Concepts for Fighting Complexity

Ousterhout's book, **[[A Philosophy of Software Design - John Ousterhout]]**, provides a framework for tackling these issues. It's not about specific technologies; it's about a mindset.

*   **Modules Should Be DEEP**
    *   The best modules have a simple, clean surface area (interface) that hides a ton of implementation complexity.
    *   **Goal:** Maximize functionality, minimize the cognitive load for the consumer. Think of a Unix `open()` call vs. the spaghetti of Java's `FileInputStream(new BufferedInputStream(...))`.

*   **"Design it Twice"**
    *   Before committing to a design for a new module, sketch out at least one serious alternative. This forces you to see the trade-offs and invariably leads to a better, more robust design than just running with your first idea.

*   **Define Errors Out of Existence**
    *   Instead of adding layers of complex error-handling, redefine a method's contract so that "error" conditions become normal behavior.
    *   *Example:* Instead of throwing an error when trying to delete a non-existent item, the method should just... do nothing. The desired state (the item doesn't exist) is already achieved.

*   **Comments as a Design Tool**
    *   Write comments *before* or *during* the implementation, not after. If a method or class is hard to explain in a simple sentence, the design is too complex. The comment is your "canary in the coal mine" for complexity.

### Takeaways

1.  **Complexity is Death by a Thousand Cuts.**
    Great design isn't one brilliant architectural decision. It's hundreds of small, good decisions. We have to sweat the small stuff—like choosing a precise variable name—because it's the accumulation of "small messes" that grinds systems to a halt.

2.  **Be Strategic, Not Just Tactical.**
    Resist the urge to find "the smallest possible change to get the ticket closed." Adopt an investment mindset: spend an extra 10% of time *now* to refactor and improve the design. This investment pays for itself incredibly quickly in future development speed and fewer bugs.

3.  **Reason from First Principles, Don't Just Follow Rules.**
    A rule like "methods should be 5 lines max" can be useful, but can also lead to horrible designs where simple logic is scattered across a dozen files. Always ask: "Does this change *actually* reduce overall complexity?" If the answer is no, challenge the rule.

4.  **The Goal is OBVIOUS Code.**
    Obvious code is code where a new reader's first guess about what it does is correct. It's the ultimate sign of a clean design. It requires less documentation and is far easier to change safely.

5.  **Why AI Won't Save Us From Bad Design.**
    AI is getting great at writing "tactical" code—the body of a function. But it can't do the strategic work of high-level design: decomposing a system into deep modules, defining clean abstractions, and making opinionated trade-offs. That's *our* job, and it's becoming more critical than ever.
