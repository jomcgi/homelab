# Roast Changelog for ColinCee/homelab

**Date**: 2026-04-16
**Status**: Approved

## Problem

We have hourly changelog summaries for jomcgi/homelab that post to Discord. We want the same for a friend's public repo (ColinCee/homelab) — but with a roasting tone, posted every 3 hours to the same channel.

## Approach

Generalize `run_changelog_iteration()` to accept a config object instead of reading env vars. Use a list-based config in Helm values with a single `CHANGELOG_CONFIGS` JSON env var. Prompts are referenced by key and defined in Python code.

## Design

### ChangelogConfig dataclass

New frozen dataclass in `changelog.py`:

```python
@dataclasses.dataclass(frozen=True)
class ChangelogConfig:
    name: str
    github_repo: str
    channel_id: str
    prompt: str              # key into PROMPTS dict
    embed_title: str
    embed_color: int
    interval_hours: int = 1
    commit_filter: re.Pattern | None = None  # None = all commits
```

### Prompt registry

Prompts live in Python code, referenced by key from config:

```python
PROMPTS: dict[str, str] = {
    "professional": "You are a changelog writer for a Kubernetes homelab project...",
    "roast": "You are Colin's close friend and a cynical senior engineer...",
}
```

The prompt template uses `{commits}` as a placeholder for the formatted commit list.

### Refactored functions

`_summarize_with_gemma` takes the prompt template from `PROMPTS[config.prompt]` instead of hardcoding it.

`_build_embed` takes `title` and `color` parameters instead of hardcoding them.

`run_changelog_iteration` takes a `ChangelogConfig` instead of reading env vars. Uses `config.interval_hours` for lookback, applies `config.commit_filter` if set.

### Config loading

`load_changelog_configs()` parses `CHANGELOG_CONFIGS` env var (JSON list) into `list[ChangelogConfig]`. Each entry maps to the dataclass fields. The `commitFilter` field in JSON is optional — when present, it's compiled to a regex pattern.

### Scheduled jobs

One job registered per config entry in `summarizer.py`:

- Job name: `f"chat.changelog.{config.name}"` (e.g. `chat.changelog.homelab`, `chat.changelog.roast`)
- Interval: `config.interval_hours * 3600`
- Aligned to interval boundaries

### Helm values

```yaml
chat:
  changelogs:
    - name: "homelab"
      channelId: "1491186550472708117"
      githubRepo: "jomcgi/homelab"
      prompt: "professional"
      embedTitle: "Homelab Changelog"
      embedColor: "0x2ECC71"
      intervalHours: 1
      commitFilter: "^(feat)(\\(.+?\\))?!?:\\s"
    - name: "roast"
      channelId: "1491186550472708117"
      githubRepo: "ColinCee/homelab"
      prompt: "roast"
      embedTitle: "Colin's Homelab Roast"
      embedColor: "0xE74C3C"
      intervalHours: 3
```

### Deployment template

Replaces `CHANGELOG_CHANNEL_ID` + `CHANGELOG_GITHUB_REPO` with a single JSON env var:

```yaml
{{- if .Values.chat.changelogs }}
- name: CHANGELOG_CONFIGS
  value: {{ .Values.chat.changelogs | toJson | quote }}
{{- end }}
```

`GITHUB_TOKEN` stays as-is — shared across all changelog configs.

### Roast prompt

```
You are Colin's close friend and a cynical senior engineer who has seen
too many homelabs. You're reviewing his recent git commits to roast him
in the group chat. He can take it — don't soften anything.

Below are his recent commits:
<commits>
{commits}
</commits>

Write a changelog-style roast. Format:

Colin homelab changelog:
- <entry>
- <entry>
- <entry>

3-5 entries. Each one is a single line written as if it's a real
changelog bullet, but the content is the roast. Examples of the shape:
- "Added three ADRs to justify turning a Beelink on."
- "Replaced working Grafana dashboard with a worse one. Wrote a runbook about it."
- "Four commits to fix one typo. Copilot did the last three."

Target specific things in the commits — pretentious messages, features
added then ripped out, yak-shaving, ADRs for three lines of YAML,
Copilot cleaning up after him, enterprise patterns on a mini-PC,
README brags that are one commit old, bike-shedding. Name the thing.

Rules:
- Past tense, declarative, changelog voice. No "Colin did X" — the
  entries are the changes themselves, deadpan.
- Punch at choices, not at him. "Docker Swarm in 2026" is fair.
  Personal attacks are lazy.
- Dry > loud. A good callback to an earlier entry beats exclamation marks.
- No hedging, no "but seriously", no constructive feedback.
- No markdown headers, no emoji, no preamble or outro. Just the header
  line and bullets.
- If a commit is genuinely boring, skip it. Don't manufacture heat.
Optionally end with one entry in square brackets, e.g. [No breaking changes. Nothing worked in the first place.]
```

### Silent when empty

Same as existing — if no commits in the lookback window, no message posted.

## Files changed

1. `projects/monolith/chat/changelog.py` — add `ChangelogConfig`, `PROMPTS`, `load_changelog_configs()`, refactor functions to use config
2. `projects/monolith/chat/summarizer.py` — loop over configs, register one job per entry
3. `projects/monolith/chart/templates/deployment.yaml` — replace old env vars with `CHANGELOG_CONFIGS`
4. `projects/monolith/deploy/values.yaml` — replace `changelog` block with `changelogs` list
5. `projects/monolith/chat/changelog_test.py` — update tests for new signature, add config loading tests
