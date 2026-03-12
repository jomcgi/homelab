# Continuous Improvement Agents — Design

## Problem

The homelab repo has no automated process for improving code quality over time.
Test coverage gaps, stale READMEs, and recurring anti-patterns accumulate
silently. Failing PR checks from bot-authored PRs sit unattended.

## Solution

Four new `Agent` implementations in the existing `cluster_agents` binary.
Each agent runs on a configurable interval, checks for relevant activity,
and submits focused jobs to the orchestrator. The orchestrator spawns
Claude Code sessions that do the actual work and create PRs.

## Architecture

### Execution Model

Agents are thin dispatchers — they detect _when_ work is needed and _what_
to work on, then delegate all intelligence to the orchestrator's Claude Code
sessions. This keeps the Go code simple and testable while letting the
prompts evolve independently.

### Git Activity Gate

Three of the four agents (test-coverage, readme-freshness, rules) share a
common trigger: "have there been non-bot commits on main since my last
successful job?"

Implementation:

1. Query orchestrator for the last completed job with the agent's tag →
   extract the commit SHA from job metadata
2. Query GitHub API for the latest non-bot commit on main
3. If the SHAs match → no activity → skip
4. If different → return the commit range for the job prompt

Bot authors filtered: `ci-format-bot`, `argocd-image-updater`, `chart-version-bot`.

On first run (no previous job exists), the agent uses a reasonable default
window (e.g., last 24h of commits) rather than processing all history.

### Dedup

All agents use the existing `Escalator.hasActiveJob(tag)` check. A job is
only submitted if no PENDING/RUNNING/SUCCEEDED job exists with the same tag.
This prevents duplicate work across restarts and overlapping sweep intervals.

## Agents

### 1. TestCoverageAgent

| Field    | Value                                  |
| -------- | -------------------------------------- |
| Interval | 1 hour (env: `TEST_COVERAGE_INTERVAL`) |
| Tag      | `improvement:test-coverage`            |
| Trigger  | Git activity gate                      |
| Model    | Sonnet                                 |

**Prompt:**

```
Review files changed in commits {commitRange} on main. For each Go or Python
source file that was modified and lacks a corresponding _test file, write
tests that cover the key behaviors.

Before starting:
- Check `gh pr list --search "test"` for existing test coverage PRs
- Check `gh issue list --search "test"` for related issues
- Skip files in generated code (zz_generated.*, *_types.go deepcopy)

Create one PR per project. Use conventional commit format:
test(<project>): add coverage for <description>
```

### 2. ReadmeFreshnessAgent

| Field    | Value                                     |
| -------- | ----------------------------------------- |
| Interval | 1 week (env: `README_FRESHNESS_INTERVAL`) |
| Tag      | `improvement:readme-freshness`            |
| Trigger  | Git activity gate                         |
| Model    | Opus                                      |

**Prompt:**

```
For each projects/*/README.md, compare the README content against the actual
project structure:
- Files and directories that exist vs what's documented
- Chart.yaml fields (appVersion, description) vs README claims
- deploy/ config (application.yaml, values.yaml) vs documented setup
- Available commands and endpoints vs what the code actually exposes

Update any README where the documented structure no longer matches reality.
Do not add content that wasn't there before — only fix inaccuracies.

Before starting:
- Check `gh pr list --search "README"` for existing README PRs
- Check `gh issue list --search "README"` for related issues

Create one PR per project. Use conventional commit format:
docs(<project>): update README to match current structure
```

### 3. RulesAgent

| Field    | Value                         |
| -------- | ----------------------------- |
| Interval | 1 day (env: `RULES_INTERVAL`) |
| Tag      | `improvement:rules`           |
| Trigger  | Git activity gate             |
| Model    | Opus                          |

**Prompt:**

```
Review PRs merged to main in commits {commitRange}. For each merged PR:

1. If it's a bug fix (fix: prefix), analyze the diff for patterns that could
   be caught statically. Propose a semgrep rule in bazel/semgrep/rules/ with
   a test case. Check existing rules to avoid duplicates.

2. If it reveals an agent anti-pattern or a common mistake, propose additions
   to .claude/CLAUDE.md or .claude/settings.json hooks to prevent recurrence.

Before starting:
- Check `gh pr list --search "semgrep OR rule OR hook"` for existing work
- Check `gh issue list` for related issues
- Review existing rules in bazel/semgrep/rules/ and .claude/settings.json

Create one PR per rule/config change. Use conventional commit format:
- build(semgrep): add rule for <pattern>
- ci(claude): add hook to prevent <behavior>
```

### 4. PRFixAgent

| Field    | Value                                           |
| -------- | ----------------------------------------------- |
| Interval | 1 hour (env: `PR_FIX_INTERVAL`)                 |
| Tag      | `improvement:pr-fix:{pr-number}`                |
| Trigger  | Open PRs with failing checks, last push >1h ago |
| Model    | Sonnet                                          |

**Collect:** Query GitHub API for open PRs where:

- Latest check suite status is `failure`
- Last push timestamp is older than 1 hour
- No active orchestrator job with tag `improvement:pr-fix:{number}`

Returns one finding per broken PR.

**Prompt (per PR):**

```
PR #{number} has failing CI checks on branch {branch}.

1. Check out the branch
2. Use BuildBuddy MCP tools to understand the CI failure
3. Fix the issue
4. Commit and push (do NOT force push)

Before starting:
- Run `gh pr view {number} --json commits,body` to understand context
- Check PR comments for any human instructions or "do not auto-fix" labels

Use conventional commit format:
fix({scope}): resolve CI failure in PR #{number}
```

## File Structure

```
cluster_agents/
├── main.go                        # Wire up all agents
├── model.go                       # Agent interface (unchanged)
├── runner.go                      # Runner (unchanged)
├── escalator.go                   # Escalator (unchanged)
├── patrol.go                      # Existing patrol agent
├── git_activity_gate.go           # Shared commit-tracking via orchestrator
├── git_activity_gate_test.go
├── github_client.go               # GitHub API client (commits, PRs, checks)
├── github_client_test.go
├── test_coverage_agent.go         # Agent 1
├── test_coverage_agent_test.go
├── readme_freshness_agent.go      # Agent 2
├── readme_freshness_agent_test.go
├── rules_agent.go                 # Agent 3
├── rules_agent_test.go
├── pr_fix_agent.go                # Agent 4
└── pr_fix_agent_test.go
```

## Configuration

New environment variables (added to cluster-agents deployment values):

| Variable                    | Default                                                | Description                                  |
| --------------------------- | ------------------------------------------------------ | -------------------------------------------- |
| `GITHUB_TOKEN`              | (required)                                             | GitHub API access — via 1Password operator   |
| `GITHUB_REPO`               | `jomcgi/homelab`                                       | Repository to monitor                        |
| `TEST_COVERAGE_INTERVAL`    | `1h`                                                   | TestCoverageAgent sweep interval             |
| `README_FRESHNESS_INTERVAL` | `168h`                                                 | ReadmeFreshnessAgent sweep interval (1 week) |
| `RULES_INTERVAL`            | `24h`                                                  | RulesAgent sweep interval                    |
| `PR_FIX_INTERVAL`           | `1h`                                                   | PRFixAgent sweep interval                    |
| `PR_FIX_STALE_THRESHOLD`    | `1h`                                                   | Min time since last push before fixing a PR  |
| `BOT_AUTHORS`               | `ci-format-bot,argocd-image-updater,chart-version-bot` | Comma-separated bot authors to ignore        |

## Dedup Summary

| Agent           | Tag pattern                    | Effect                   |
| --------------- | ------------------------------ | ------------------------ |
| TestCoverage    | `improvement:test-coverage`    | One active job at a time |
| ReadmeFreshness | `improvement:readme-freshness` | One active job at a time |
| Rules           | `improvement:rules`            | One active job at a time |
| PRFix           | `improvement:pr-fix:{number}`  | One active job per PR    |

## Non-Goals

- Running tests locally — CI handles that
- Modifying cluster state — all changes go through GitOps PRs
- Replacing human review — agents create PRs, humans merge
