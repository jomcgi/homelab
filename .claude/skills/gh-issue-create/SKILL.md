---
name: gh-issue-create
description: Convert a design doc (ideas/*.md) into a parent GitHub issue with child sub-issues. Use this to bootstrap work from design documents.
---

# Create GitHub Issues from Design Doc

This skill converts a design document into structured GitHub Issues for autonomous execution.

## Workflow

1. **Read** the design doc
2. **Analyze** to identify discrete, atomic tasks
3. **Create parent issue** linking to the doc
4. **Create child issues** and link them as sub-issues
5. **Label** parent as `agent-ready`

## Usage

```
/gh-issue-create ideas/agent-controller.md
```

Or via controller prompt:

```bash
claude "Use /gh-issue-create to convert ideas/agent-controller.md into GitHub issues"
```

## Step 1: Read the Design Doc

```bash
cat ~/repos/homelab/ideas/<design-doc>.md
```

Identify:

- **Goal**: What does "done" look like?
- **Phases**: Major milestones or stages
- **Tasks**: Discrete, implementable units of work
- **Dependencies**: Which tasks depend on others (implicit ordering)

## Step 2: Create Parent Issue

```bash
REPO="jomcgi/homelab"
DESIGN_DOC="ideas/agent-controller.md"
TITLE="Implement Agent Controller"

PARENT_URL=$(gh issue create \
    --repo "$REPO" \
    --title "$TITLE" \
    --body "$(cat <<'EOF'
## Context

Design doc: `ideas/agent-controller.md`

## Goal

<!-- Extract from design doc -->

## Constraints

<!-- Extract from design doc -->

## Progress

Sub-issues will be created below. Work them in logical order based on dependencies.
EOF
)")

# Extract parent issue number from URL
PARENT=$(echo "$PARENT_URL" | grep -oE '[0-9]+$')
echo "Created parent issue #$PARENT"
```

## Step 3: Create Child Issues as Sub-Issues

**IMPORTANT:** The `gh` CLI does not have a `--parent` flag. You must use the REST API to link sub-issues.

For each discrete task identified:

```bash
# 1. Create the child issue
CHILD_URL=$(gh issue create \
    --repo "$REPO" \
    --title "Create controller.sh script" \
    --body "$(cat <<'EOF'
## Task

Implement the controller shell script that polls GitHub issues and spawns Claude sessions.

## Acceptance Criteria

- [ ] Script polls for issues with `agent-ready` label
- [ ] Script checks lock status before claiming
- [ ] Script spawns tmux session with Claude
- [ ] Script handles concurrent session limits

## Files Likely Involved

- charts/claude/src/controller.sh (new)

## Reference

See parent issue for full design context.
EOF
)")

# 2. Extract child issue number
CHILD_NUMBER=$(echo "$CHILD_URL" | grep -oE '[0-9]+$')

# 3. Get the numeric ID (NOT the node_id) - this is required by the API
CHILD_ID=$(gh api "repos/$REPO/issues/$CHILD_NUMBER" --jq '.id')

# 4. Link as sub-issue to parent
gh api "repos/$REPO/issues/$PARENT/sub_issues" --method POST -F sub_issue_id="$CHILD_ID"

echo "Created and linked child issue #$CHILD_NUMBER"
```

Repeat for each task.

## Step 4: Label Parent as Ready

Once all children are created and linked:

```bash
gh issue edit "$PARENT" --repo "$REPO" --add-label "agent-ready"
```

**Note:** If the `agent-ready` label doesn't exist, create it first:

```bash
gh label create "agent-ready" --repo "$REPO" --description "Issue ready for autonomous agent pickup" --color "2ea44f"
```

## Task Decomposition Guidelines

### Good Child Issues

- **Atomic**: One logical change
- **Self-contained**: Has enough context to implement independently
- **Testable**: Clear success criteria
- **Right-sized**: Can be completed in one session (< 30 min typical)

### Examples

From `ideas/agent-controller.md`:

| Child Issue                            | Why It's Good                       |
| -------------------------------------- | ----------------------------------- |
| "Create controller.sh script"          | Single file, clear scope            |
| "Add controller Kubernetes deployment" | Single manifest, depends on script  |
| "Add controller values.yaml config"    | Clear scope, complements deployment |
| "Test end-to-end flow"                 | Validation step, depends on others  |

### Anti-patterns

| Bad                                | Better                                |
| ---------------------------------- | ------------------------------------- |
| "Implement controller" (too broad) | Split into script, deployment, config |
| "Fix bugs" (vague)                 | Specific: "Handle GitHub API timeout" |
| "Add tests and docs" (two things)  | Separate: "Add tests", "Add docs"     |

## Ordering Hints

Include ordering hints in child issue descriptions when dependencies exist:

```markdown
## Task

Add Kubernetes deployment manifest for the controller.

## Dependencies

This should be worked AFTER "Create controller.sh script" is complete,
as the deployment references the script.
```

Claude will read all children and reason about the correct order.

## Complete Example

```bash
#!/bin/bash
# Bootstrap issues from design doc
set -euo pipefail

REPO="jomcgi/homelab"
DESIGN_DOC="ideas/agent-controller.md"

# Helper function to create a child issue and link it as sub-issue
create_child() {
    local parent=$1
    local title=$2
    local body=$3

    # Create the issue
    local child_url=$(gh issue create --repo "$REPO" --title "$title" --body "$body")
    local child_number=$(echo "$child_url" | grep -oE '[0-9]+$')

    # Get numeric ID and link as sub-issue
    local child_id=$(gh api "repos/$REPO/issues/$child_number" --jq '.id')
    gh api "repos/$REPO/issues/$parent/sub_issues" --method POST -F sub_issue_id="$child_id" --silent

    echo "  Created #$child_number: $title"
}

# Create parent issue
echo "Creating parent issue..."
PARENT_URL=$(gh issue create \
    --repo "$REPO" \
    --title "Implement Agent Controller" \
    --body "## Context
Design doc: \`$DESIGN_DOC\`

## Goal
Autonomous GitHub issue execution via polling controller.

## Constraints
- Simple shell script preferred
- Must handle lock TTL
- Single controller instance

## Progress
Sub-issues track individual tasks. Work them in order based on phase dependencies.")

PARENT=$(echo "$PARENT_URL" | grep -oE '[0-9]+$')
echo "Created parent issue #$PARENT"

# Create and link children
echo "Creating child issues..."

create_child "$PARENT" "Create controller.sh script" "Implement polling loop, lock checking, session spawning.

## Acceptance Criteria
- [ ] Polls for agent-ready issues
- [ ] Checks/cleans stale locks
- [ ] Spawns tmux sessions
- [ ] Respects MAX_CONCURRENT limit"

create_child "$PARENT" "Add controller Kubernetes deployment" "Create deployment manifest for controller.

## Dependencies
Work AFTER controller.sh is complete.

## Acceptance Criteria
- [ ] Deployment runs controller.sh
- [ ] Mounts repo PVC
- [ ] Has GitHub token secret"

create_child "$PARENT" "Add controller values.yaml configuration" "Add configuration options to values.yaml.

## Acceptance Criteria
- [ ] pollInterval configurable
- [ ] lockTTL configurable
- [ ] maxConcurrent configurable
- [ ] enabled flag for opt-in"

create_child "$PARENT" "Test end-to-end flow" "Validate the complete workflow.

## Dependencies
Work AFTER all other children complete.

## Acceptance Criteria
- [ ] Controller picks up test issue
- [ ] Claude session executes successfully
- [ ] Issue is closed on completion"

# Mark parent as ready
gh issue edit "$PARENT" --repo "$REPO" --add-label "agent-ready"

echo "Done! Parent #$PARENT is ready for agent pickup."
```

## Controller Integration

The controller can bootstrap new work by running:

```bash
claude "Use /gh-issue-create to convert ideas/$DESIGN_DOC into GitHub issues, \
then use /gh-issue to start working on them."
```

Or as separate steps:

1. Human or scheduled job runs `/gh-issue-create` on new design docs
2. Controller polls for `agent-ready` issues
3. Controller spawns Claude with `/gh-issue` to execute

## Tips

- **Read the whole doc** before creating issues - understand the full scope
- **Err on fewer children** - can always add more later
- **Include acceptance criteria** - makes "done" unambiguous
- **Link to design doc** - parent issue should always reference source
- **Don't over-specify** - Claude can figure out details from context
