# Claude Code: Advanced Workflows for Developer Productivity

**Week 2 — Beyond the Basics**

> Last week: What are agents, skills, config (CLAUDE.md), and MCPs?
> This week: Real examples of skills, hooks, agents, and workflows that make devs faster.

---

## Slide 1: Recap — The Building Blocks

| Concept       | One-liner                                                  |
| ------------- | ---------------------------------------------------------- |
| **CLAUDE.md** | Project instructions that shape every Claude conversation   |
| **Skills**    | Reusable, domain-specific prompts Claude can invoke         |
| **Hooks**     | Shell scripts that run before/after tool use — guardrails   |
| **MCPs**      | External tool servers (K8s, ArgoCD, SigNoz) Claude can call |
| **Agents**    | Specialized sub-agents with focused domain knowledge        |

Today we go deeper into each one with real examples.

---

## Slide 2: Skills — Codifying Tribal Knowledge

**Problem:** Repetitive multi-step tasks that every dev does slightly differently.

**Solution:** Skills are markdown files (`.claude/skills/<name>/SKILL.md`) that encode the *exact* steps, patterns, and gotchas for a task.

### Example: `/add-service` — Scaffold a New Service

Instead of copy-pasting from another service and forgetting half the config:

```
> /add-service my-cool-app
```

Claude automatically creates:
- `projects/my-cool-app/deploy/application.yaml` — ArgoCD Application
- `projects/my-cool-app/deploy/kustomization.yaml` — Makes it discoverable
- `projects/my-cool-app/deploy/values.yaml` — Helm value overrides

All following the repo's exact conventions (namespace naming, chart source, sync policy).

### Example: `/add-httpcheck-alert` — Monitoring in One Command

```
> /add-httpcheck-alert
```

Claude creates a SigNoz HTTP health check alert with the correct JSON schema, thresholds, and notification channels — no need to remember the SigNoz API format.

### Example: `/adr` — Architecture Decision Records

```
> /adr
```

Generates a structured ADR in `docs/decisions/<category>/` with sections for problem, proposal, architecture, risks, and references. Consistent format every time.

### Why This Matters

- **Onboarding:** New devs can `/add-service` on day one without reading 5 docs
- **Consistency:** Every service follows the same patterns
- **Speed:** 30-second scaffolding vs. 15 minutes of copy-paste-modify

---

## Slide 3: Hooks — Automated Guardrails

**Problem:** Developers (and Claude) make mistakes — running the wrong command, forgetting to update a related file, writing to the wrong branch.

**Solution:** `PreToolUse` hooks in `settings.json` intercept tool calls *before* they execute.

### Real Hook Examples from This Repo

#### 1. "Use MCP, Not kubectl" — `prefer-k8s-mcp.sh`

```
Matcher: Bash
Trigger: Any kubectl get/describe/logs/top command
Action: BLOCK — tells Claude to use the Kubernetes MCP tool instead
```

**Why:** MCP tools are auditable, structured, and don't need kubeconfig on the dev machine. The hook enforces this without relying on Claude remembering.

#### 2. "Don't Write to Main" — `check-plan-worktree.sh`

```
Matcher: Write|Edit
Trigger: Writing plan/design files
Action: BLOCK if not in a git worktree (i.e., on main branch)
```

**Why:** Plans must land on feature branches, not main. The hook catches this before any file is written.

#### 3. "Keep Chart Versions in Sync" — `check-chart-version-sync.sh`

```
Matcher: Write|Edit
Trigger: Editing Chart.yaml or application.yaml
Action: WARN if Chart.yaml version doesn't match application.yaml targetRevision
```

**Why:** A version mismatch means ArgoCD deploys a stale chart. This is a subtle bug that the hook catches instantly.

#### 4. "Don't Push to Merged PRs" — `check-stale-pr.sh`

```
Matcher: Bash
Trigger: git push commands
Action: BLOCK if the PR for this branch is already merged
```

**Why:** Pushing to a merged branch creates confusion. The hook prevents wasted work.

### The Pattern

```
hooks → catch mistakes before they happen → no cleanup needed
```

Hooks are cheap to write (small shell scripts) and save hours of debugging.

---

## Slide 4: MCP Servers — Claude Talks to Your Infrastructure

**Problem:** Investigating production issues requires switching between kubectl, ArgoCD UI, SigNoz dashboards, and build logs.

**Solution:** MCP servers expose your infrastructure as tools Claude can call directly.

### What's Connected in This Repo

| MCP Server             | What Claude Can Do                                          |
| ---------------------- | ----------------------------------------------------------- |
| **Kubernetes**         | List/get resources, pod logs, node metrics, events          |
| **ArgoCD**             | List/sync apps, view resource trees, check sync status      |
| **SigNoz**             | Search logs/traces, query metrics, check alerts, dashboards |
| **Agent Orchestrator** | Submit/monitor background agent jobs                        |

### Demo Scenario: "Why Is My Service Down?"

Without Claude + MCPs:
```bash
kubectl get pods -n myapp          # what's the pod status?
kubectl describe pod myapp-xxx     # why is it failing?
kubectl logs myapp-xxx             # what do the logs say?
argocd app get myapp               # is ArgoCD in sync?
# open SigNoz... click around... find the trace...
```

With Claude + MCPs:
```
> My service myapp seems to be having issues. Can you investigate?
```

Claude autonomously:
1. Checks ArgoCD sync status
2. Lists pods and finds the failing one
3. Pulls recent logs
4. Searches SigNoz for error traces
5. Correlates and gives you a root cause summary

**One prompt replaces 5+ tool switches.**

---

## Slide 5: Agents — Specialized Sub-Claude Instances

**Problem:** A generalist Claude doesn't know your repo's specific patterns for Go, Python, Helm, security, etc.

**Solution:** `AGENTS.md` defines specialized agents with domain-specific instructions.

### Agents Defined in This Repo

| Agent              | Speciality                                       |
| ------------------ | ------------------------------------------------ |
| **container**      | OCI images with apko (not Dockerfiles)           |
| **golang**         | Go operators/controllers with controller-runtime |
| **python**         | Python with aspect_rules_py (not rules_python)   |
| **security**       | Kyverno policies, 1Password secrets, non-root    |
| **argocd**         | GitOps patterns, Application CRDs               |
| **vite**           | Frontend with Vite/React/Tailwind               |
| **reviewer**       | Code review checklists per change type           |
| **observability**  | SigNoz investigation, MCP tool usage             |
| **cloudflare**     | Custom Cloudflare tunnel operator                |
| **linkerd**        | Service mesh debugging                           |

### Why Agents Matter

Without agents: Claude might suggest `pip install` (wrong — use Bazel), `docker build` (wrong — use apko), or `rules_python` syntax (wrong — use `aspect_rules_py`).

With agents: The Python agent *already knows* the repo uses `@pip//package` and `aspect_rules_py`. No correction needed.

---

## Slide 6: Permissions — Controlled Autonomy

**Problem:** You want Claude to be autonomous *enough* but not run dangerous commands.

**Solution:** `settings.json` permissions whitelist exactly which tools and commands are pre-approved.

### Example Permission Structure

```jsonc
{
  "permissions": {
    "allow": [
      "Bash(git status:*)",     // Always safe
      "Bash(git push:*)",       // Pre-approved (hooks add safety)
      "Bash(gh:*)",             // GitHub CLI
      "Bash(format:*)",         // Code formatting
      "Bash(helm template:*)",  // Render templates (read-only)
      "Bash(bb:*)",             // BuildBuddy CI CLI
      "mcp__context-forge__*"   // All MCP tools
    ]
  }
}
```

**Not on the list?** Claude asks for permission first. This includes:
- `kubectl apply/delete/patch` — blocked entirely (GitOps only)
- `rm`, `docker`, arbitrary scripts — require explicit approval

### The Philosophy

> **Approve the safe stuff once. Block the dangerous stuff always. Ask about everything else.**

---

## Slide 7: Templates — Structured Thinking

**Problem:** Design docs, bug reports, and runbooks all look different depending on who writes them.

**Solution:** `.claude/templates/` provides markdown templates Claude uses automatically.

### Available Templates

| Template                         | Use Case                                    |
| -------------------------------- | ------------------------------------------- |
| `design-template.md`            | Technical design with architecture sections |
| `tasks-template.md`             | Implementation plan with atomic tasks       |
| `bug-analysis-template.md`      | Root cause analysis framework               |
| `bug-report-template.md`        | Structured bug reporting                    |
| `runbook-alert-template.md`     | Alert handling and triage steps             |
| `runbook-ci-failure-template.md`| CI failure debugging playbook               |
| `project_plan.md`               | Full project plan with phases               |

Claude picks the right template based on context — ask for a design doc and it uses `design-template.md` automatically.

---

## Slide 8: Putting It All Together — A Real Workflow

### Scenario: "Add a new microservice to the cluster"

**Step 1: Scaffold** (Skill)
```
> /add-service payment-gateway
```
Creates ArgoCD app, kustomization, and values files.

**Step 2: Add monitoring** (Skill)
```
> /add-httpcheck-alert for payment-gateway on /healthz
```
Creates SigNoz health check alert.

**Step 3: Add auto image updates** (Skill)
```
> /add-image-updater for payment-gateway
```
Configures ArgoCD Image Updater for automatic digest-based deploys.

**Step 4: Record the decision** (Skill)
```
> /adr for why we chose payment-gateway architecture
```
Creates an Architecture Decision Record.

**Step 5: Push and verify** (Hooks + MCP)
- Hook ensures we're on a feature branch
- Hook validates chart version sync
- After merge, Claude uses ArgoCD MCP to verify the app syncs
- Claude uses SigNoz MCP to confirm the health check is green

**Total time: ~5 minutes for what used to take an hour.**

---

## Slide 9: CI Integration — `/buildbuddy`

**Problem:** CI fails and you spend 20 minutes digging through logs to find the one failing test.

**Solution:** The `/buildbuddy` skill + `bb` CLI gives Claude direct access to CI.

```
> /buildbuddy — CI is failing on my PR, help me debug it
```

Claude can:
- `bb view` — See the latest build status
- `bb print` — Get full build logs
- `bb ask` — Ask natural language questions about the build failure
- Reproduce remotely: `bb remote test //... --config=ci`

No more context-switching to the CI dashboard.

---

## Slide 10: Key Takeaways

### 1. Skills = Codified Tribal Knowledge
Turn your team's "how we do things" into repeatable commands.

### 2. Hooks = Automated Guardrails
Catch mistakes before they happen. Cheap to write, expensive bugs prevented.

### 3. MCPs = Infrastructure as Tools
Let Claude talk to your cluster, observability, and CI directly.

### 4. Agents = Domain Experts on Demand
Specialized knowledge for each tech stack in your repo.

### 5. Templates = Consistent Output
Every design doc, bug report, and runbook follows the same structure.

### The Compound Effect

Each piece is useful alone. Together, they create a development environment where Claude understands your repo's conventions, enforces them automatically, and accelerates every task.

---

## Slide 11: Getting Started — What to Build First

| Priority | What to Build                     | Effort | Impact |
| -------- | --------------------------------- | ------ | ------ |
| 1        | **CLAUDE.md** with repo patterns  | 30 min | High   |
| 2        | **Hooks** for your top 3 mistakes | 1 hour | High   |
| 3        | **Skills** for repeated tasks     | 1 hour | High   |
| 4        | **MCP servers** for your infra    | varies | Medium |
| 5        | **Agents** for each tech stack    | 1 hour | Medium |
| 6        | **Templates** for docs            | 30 min | Low    |

Start with CLAUDE.md — it's the foundation everything else builds on.

---

## Discussion / Q&A

Topics to explore:
- What repetitive tasks could become skills in your team?
- What mistakes do your hooks need to catch?
- What infrastructure tools would benefit from MCP integration?
