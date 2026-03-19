# Pipeline Output Per-Step Filtering — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split pipeline job output into per-step accordion sections with clickable node navigation and markdown rendering.

**Architecture:** Backend `cleanOutput()` strips all goose banners and goose-result blocks. Frontend splits the cleaned output on `--- pipeline step N: agent ---` markers, renders each chunk in a collapsible accordion section via `react-markdown`, and makes `PipelineFlow` nodes clickable for scroll-to navigation.

**Tech Stack:** Go (backend), React 19 + react-markdown (frontend), pnpm

---

### Task 1: Backend — Strip All Goose Banners

The current `cleanOutput()` only strips content up to the **first** `goose is ready` marker. Pipeline jobs spawn a new goose process per step, so each step has its own banner. Enhance to strip all occurrences.

**Files:**

- Modify: `projects/agent_platform/orchestrator/clean.go`
- Modify: `projects/agent_platform/orchestrator/clean_test.go`

**Step 1: Write the failing test**

Add to `clean_test.go`:

```go
func TestCleanOutput_MultipleBanners(t *testing.T) {
	raw := "   L L\tgoose is ready\nStep 0 output\n\n--- pipeline step 0: research ---\n  __( O)>  blah\n \\____)\t20260318_1\n   L L\tgoose is ready\nStep 1 output\n"
	got := cleanOutput(raw)
	want := "Step 0 output\n\n--- pipeline step 0: research ---\nStep 1 output\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}
```

**Step 2: Run test to verify it fails**

CI runs tests remotely. Push to branch and check, or verify logic locally — the current `cleanOutput()` uses `strings.Index` (finds first), so subsequent banners will remain.

**Step 3: Modify `cleanOutput()` to strip all banners**

Replace the single-banner stripping in `clean.go` with a loop:

```go
func cleanOutput(raw string) string {
	s := ansiRE.ReplaceAllString(raw, "")

	// Normalize line endings: \r\n → \n, then lone \r → \n.
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")

	// Strip ALL Goose startup banners (one per pipeline step).
	for {
		idx := strings.Index(s, gooseBannerEnd)
		if idx == -1 {
			break
		}
		// Find the start of this banner block — scan backwards to find
		// the beginning of the ASCII art lines (lines containing __( O)> or \____)
		// or simply strip from the last newline before the banner art.
		bannerStart := idx
		// Walk backwards to find the start of banner lines.
		// Banner is typically 3 lines: __( O)>, \____), L L goose is ready
		// Find the earliest consecutive banner line.
		lines := s[:idx]
		lineStart := strings.LastIndex(lines, "\n")
		if lineStart == -1 {
			lineStart = 0
		} else {
			lineStart++ // skip the \n itself
		}
		// Check up to 3 lines before "goose is ready" for banner art
		for range 3 {
			prev := strings.LastIndex(s[:lineStart], "\n")
			if prev == -1 {
				candidate := s[:lineStart]
				if isBannerLine(candidate) {
					lineStart = 0
				}
				break
			}
			candidate := s[prev+1 : lineStart]
			if isBannerLine(candidate) {
				lineStart = prev + 1
			} else {
				break
			}
		}
		bannerStart = lineStart

		after := idx + len(gooseBannerEnd)
		if after < len(s) && s[after] == '\n' {
			after++
		}
		s = s[:bannerStart] + s[after:]
	}

	return strings.TrimLeft(s, "\n")
}

// isBannerLine returns true if the line looks like part of the goose ASCII art banner.
func isBannerLine(line string) bool {
	trimmed := strings.TrimSpace(line)
	return strings.Contains(trimmed, "__( O)>") ||
		strings.Contains(trimmed, "\\____)") ||
		strings.Contains(trimmed, "L L")
}
```

**Step 4: Run tests to verify all pass**

Push to branch — CI runs `bazel test //projects/agent_platform/orchestrator:orchestrator_unit_test`.

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/clean.go projects/agent_platform/orchestrator/clean_test.go
git commit -m "fix(orchestrator): strip all goose banners from pipeline output"
```

---

### Task 2: Backend — Strip goose-result Blocks from Output

Remove `goose-result` fenced blocks from the display output. The structured data is already parsed and stored in `Attempt.Result` by `parseGooseResult()`.

**Files:**

- Modify: `projects/agent_platform/orchestrator/clean.go`
- Modify: `projects/agent_platform/orchestrator/clean_test.go`

**Step 1: Write the failing test**

Add to `clean_test.go`:

````go
func TestCleanOutput_StripsGooseResult(t *testing.T) {
	raw := "Some analysis here\n\n```goose-result\ntype: pr\nurl: https://github.com/jomcgi/homelab/pull/42\nsummary: Fixed the thing\n```\n"
	got := cleanOutput(raw)
	want := "Some analysis here\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}

func TestCleanOutput_StripsMultipleGooseResults(t *testing.T) {
	raw := "Step 0\n```goose-result\ntype: gist\nurl: https://gist.github.com/abc\nsummary: Research\n```\n\n--- pipeline step 0: research ---\nStep 1\n```goose-result\ntype: pr\nurl: https://github.com/jomcgi/homelab/pull/1\nsummary: Fix\n```\n"
	got := cleanOutput(raw)
	want := "Step 0\n\n--- pipeline step 0: research ---\nStep 1\n"
	if got != want {
		t.Errorf("cleanOutput() = %q, want %q", got, want)
	}
}
````

**Step 2: Add goose-result stripping to `cleanOutput()`**

Add after the banner stripping loop in `clean.go`:

````go
	// Strip ```goose-result ... ``` fenced blocks.
	const resultStart = "```goose-result\n"
	const resultEnd = "\n```"
	for {
		idx := strings.Index(s, resultStart)
		if idx == -1 {
			break
		}
		endContent := s[idx+len(resultStart):]
		endIdx := strings.Index(endContent, resultEnd)
		if endIdx == -1 {
			break
		}
		after := idx + len(resultStart) + endIdx + len(resultEnd)
		// Also consume trailing newline if present.
		if after < len(s) && s[after] == '\n' {
			after++
		}
		s = s[:idx] + s[after:]
	}
````

**Step 3: Run tests to verify all pass**

Push to branch — CI validates.

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/clean.go projects/agent_platform/orchestrator/clean_test.go
git commit -m "feat(orchestrator): strip goose-result blocks from display output"
```

---

### Task 3: Frontend — Add react-markdown Dependency

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/package.json`
- Modify: `pnpm-lock.yaml` (auto-updated)
- Modify: `projects/agent_platform/orchestrator/ui/BUILD`

**Step 1: Install react-markdown**

```bash
cd /tmp/claude-worktrees/pipeline-output-per-step
pnpm --filter agent-orchestrator-ui add react-markdown
```

**Step 2: Add to BUILD deps**

In `projects/agent_platform/orchestrator/ui/BUILD`, add `"react-markdown"` to the `deps` list in `vite_build`:

```starlark
    deps = [
        "react",
        "react-dom",
        "react-markdown",
        "vite",
        "@vitejs/plugin-react",
    ],
```

**Step 3: Run `format` to regenerate BUILD files**

```bash
format
```

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/package.json projects/agent_platform/orchestrator/ui/BUILD pnpm-lock.yaml
git commit -m "build(orchestrator-ui): add react-markdown dependency"
```

---

### Task 4: Frontend — Output Parsing Utility

Add a function to split raw output into per-step chunks using the separator markers.

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx`

**Step 1: Add the `parseStepOutput` utility**

Add after the existing utils section in `App.jsx`:

```jsx
// ─── Output parsing ──────────────────────────────────────────────────────────

const STEP_SEPARATOR = /\n--- pipeline step (\d+): (.+?) ---\n/;

/**
 * Split raw output into per-step chunks.
 * Returns [{ index, agent, content }] — one entry per pipeline step.
 * Content before the first separator (deep-plan output) is discarded.
 */
function parseStepOutput(output) {
  if (!output) return [];
  const parts = output.split(STEP_SEPARATOR);
  // parts = [preamble, index0, agent0, content0, index1, agent1, content1, ...]
  const steps = [];
  for (let i = 1; i + 2 < parts.length; i += 3) {
    steps.push({
      index: parseInt(parts[i], 10),
      agent: parts[i + 1],
      content: parts[i + 2].trim(),
    });
  }
  return steps;
}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "feat(orchestrator-ui): add parseStepOutput utility"
```

---

### Task 5: Frontend — StepAccordion Component

Create the per-step collapsible output section with markdown rendering.

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx`

**Step 1: Add the import**

At the top of `App.jsx`:

```jsx
import Markdown from "react-markdown";
```

**Step 2: Add the StepAccordion component**

Add after `parseStepOutput`:

```jsx
// ─── Step accordion ──────────────────────────────────────────────────────────

function StepAccordion({ step, plan, isOpen, onToggle, stepRef }) {
  const planStep = plan?.[step.index];
  const mappedStatus = planStep
    ? STEP_STATUS_MAP[planStep.status] || "PENDING"
    : "SUCCEEDED";
  const color = agentColor(step.agent);

  return (
    <div ref={stepRef} style={{ borderTop: "1px solid #f3f4f6" }}>
      <button
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          width: "100%",
          padding: "8px 20px",
          fontSize: 11,
          color: "#9ca3af",
          background: isOpen ? "#f9fafb" : "transparent",
          border: "none",
          cursor: "pointer",
          outline: "none",
          transition: "color 0.15s, background 0.15s",
          fontFamily: "inherit",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#374151")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#9ca3af")}
      >
        <ChevronDown size={10} open={isOpen} />
        <Dot status={mappedStatus} />
        <span
          style={{
            fontWeight: 500,
            color: color.fg,
          }}
        >
          {step.agent}
        </span>
      </button>

      {isOpen && (
        <div
          style={{
            padding: "12px 20px",
            fontSize: 12,
            lineHeight: 1.6,
            color: "#374151",
            overflow: "auto",
            maxHeight: 400,
            borderTop: "1px solid #f3f4f6",
          }}
          className="step-markdown"
        >
          {step.content ? (
            <Markdown>{step.content}</Markdown>
          ) : (
            <span style={{ color: "#d1d5db", fontStyle: "italic" }}>
              No output
            </span>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Add markdown styles to the global `<style>` block**

In the `App` component, extend the existing `<style>` block:

```css
.step-markdown h1,
.step-markdown h2,
.step-markdown h3 {
  font-size: 13px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: #1f2937;
}
.step-markdown p {
  margin: 4px 0;
}
.step-markdown ul,
.step-markdown ol {
  margin: 4px 0;
  padding-left: 20px;
}
.step-markdown code {
  font-family: monospace;
  font-size: 11px;
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 3px;
}
.step-markdown pre {
  background: #f3f4f6;
  padding: 8px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 4px 0;
}
.step-markdown pre code {
  background: none;
  padding: 0;
}
```

**Step 4: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "feat(orchestrator-ui): add StepAccordion component with markdown rendering"
```

---

### Task 6: Frontend — Clickable Pipeline Nodes

Make `PipelineFlow` nodes clickable to navigate to the matching accordion section.

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx`

**Step 1: Add `activeStep` and `onStepClick` props to PipelineFlow**

Update the `PipelineFlow` signature and add click handling:

```jsx
function PipelineFlow({ plan, activeStep, onStepClick }) {
```

Add to the agent pill `<div>`:

```jsx
onClick={(e) => {
  e.stopPropagation();
  onStepClick?.(i);
}}
style={{
  // ... existing styles ...
  cursor: onStepClick ? "pointer" : "default",
  outline: activeStep === i ? `2px solid ${color.fg}` : "none",
  outlineOffset: 1,
}}
```

**Step 2: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "feat(orchestrator-ui): make pipeline nodes clickable with active highlight"
```

---

### Task 7: Frontend — Wire Everything in JobRow

Replace the single output `<pre>` with the step accordion, wire up node clicks and scroll-to behavior.

**Files:**

- Modify: `projects/agent_platform/orchestrator/ui/src/App.jsx`

**Step 1: Add state and refs to JobRow**

Add to the top of `JobRow`:

```jsx
import { useState, useEffect, useCallback, useRef, useMemo } from "react";

// Inside JobRow:
const [activeStep, setActiveStep] = useState(null);
const stepRefs = useRef({});
const stepOutput = useMemo(
  () => (hasPlan ? parseStepOutput(attempt?.output) : []),
  [hasPlan, attempt?.output],
);
```

**Step 2: Add step click handler**

```jsx
const handleStepClick = useCallback((i) => {
  setOpen(true);
  setActiveStep((prev) => (prev === i ? null : i));
  // Scroll to the step after state update
  setTimeout(() => {
    stepRefs.current[i]?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, 50);
}, []);
```

**Step 3: Pass props to PipelineFlow**

```jsx
<PipelineFlow
  plan={job.plan}
  activeStep={activeStep}
  onStepClick={handleStepClick}
/>
```

**Step 4: Replace the output section**

Replace the existing `{/* Output toggle */}` section (lines 493-603) with:

```jsx
{
  /* Per-step output (pipeline jobs) */
}
{
  hasPlan && stepOutput.length > 0 && (
    <div>
      {stepOutput.map((step) => (
        <StepAccordion
          key={step.index}
          step={step}
          plan={job.plan}
          isOpen={activeStep === step.index}
          onToggle={() =>
            setActiveStep((prev) => (prev === step.index ? null : step.index))
          }
          stepRef={(el) => (stepRefs.current[step.index] = el)}
        />
      ))}
    </div>
  );
}

{
  /* Fallback: single output for non-pipeline jobs */
}
{
  !hasPlan && hasOutput && (
    <>
      <button
        onClick={() => setOutputOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          width: "100%",
          padding: "8px 20px",
          fontSize: 11,
          color: "#9ca3af",
          background: outputOpen ? "#f9fafb" : "transparent",
          border: "none",
          borderTop: jobSummary || job.summary ? "1px solid #f3f4f6" : "none",
          cursor: "pointer",
          outline: "none",
          transition: "color 0.15s, background 0.15s",
          fontFamily: "inherit",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#374151")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#9ca3af")}
      >
        <ChevronDown size={10} open={outputOpen} />
        Output
        {attempt?.exit_code != null && (
          <span
            style={{
              fontFamily: "monospace",
              color: attempt.exit_code === 0 ? "#22c55e" : "#f87171",
            }}
          >
            exit {attempt.exit_code}
          </span>
        )}
      </button>

      {outputOpen && (
        <div
          style={{
            padding: "12px 20px",
            fontSize: 12,
            lineHeight: 1.6,
            color: "#374151",
            overflow: "auto",
            maxHeight: 400,
            borderTop: "1px solid #f3f4f6",
          }}
          className="step-markdown"
        >
          <Markdown>{attempt?.output || ""}</Markdown>
        </div>
      )}
    </>
  );
}
```

**Step 5: Commit**

```bash
git add projects/agent_platform/orchestrator/ui/src/App.jsx
git commit -m "feat(orchestrator-ui): wire per-step accordion output with node navigation"
```

---

### Task 8: Goose Hints — Markdown Output Guidance

Tell the agent its output will be rendered as markdown.

**Files:**

- Modify: `projects/agent_platform/goose_agent/.goosehints`

**Step 1: Add output formatting section**

Append to `.goosehints`:

```markdown
## Output Formatting

Your output is rendered as markdown in a dashboard UI. Use markdown formatting
(headers, lists, code blocks) for clarity. Do not include raw terminal output
like progress bars or spinner characters.
```

**Step 2: Commit**

```bash
git add projects/agent_platform/goose_agent/.goosehints
git commit -m "feat(goose-agent): add markdown output formatting hint"
```

---

### Task 9: Chart Version Bump

Bump the orchestrator chart version and update `targetRevision` in the deploy application.

**Files:**

- Modify: `projects/agent_platform/chart/Chart.yaml`
- Modify: `projects/agent_platform/deploy/application.yaml`

**Step 1: Bump chart version**

Read both files, increment the patch version in `Chart.yaml`, and update `targetRevision` in `application.yaml` to match.

**Step 2: Commit**

```bash
git add projects/agent_platform/chart/Chart.yaml projects/agent_platform/deploy/application.yaml
git commit -m "chore(agent-platform): bump chart version"
```

---

### Task 10: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feat/pipeline-output-per-step
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(orchestrator-ui): per-step pipeline output with markdown rendering" --body "$(cat <<'EOF'
## Summary
- Enhanced `cleanOutput()` to strip all goose banners and goose-result blocks
- Split pipeline output into per-step accordion sections
- Made pipeline nodes clickable for scroll-to navigation with active highlight
- Added `react-markdown` for rendering agent output as formatted markdown
- Added `.goosehints` guidance for markdown output formatting

## Test plan
- [ ] CI passes (Go tests for cleanOutput, Bazel build for UI)
- [ ] Pipeline jobs show per-step accordion instead of single output blob
- [ ] Clicking pipeline node opens and scrolls to matching step
- [ ] Goose banners and goose-result blocks are not visible in output
- [ ] Non-pipeline jobs fall back to single output view
- [ ] Markdown formatting renders correctly (headers, lists, code blocks)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
