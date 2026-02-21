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

## Step 3: Create Child Issues and Link via Task List

**IMPORTANT:** GitHub does NOT have a `repos/$REPO/issues/$PARENT/sub_issues` API endpoint. Instead, use GitHub's task list syntax in the parent issue body.

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

- scripts/controller.sh (new)

## Reference

See parent issue for full design context.
EOF
)")

# 2. Extract child issue number
CHILD_NUMBER=$(echo "$CHILD_URL" | grep -oE '[0-9]+$')

# 3. Track child numbers to update parent body later
CHILDREN+=("$CHILD_NUMBER")

echo "Created child issue #$CHILD_NUMBER"
```

After creating all children, update parent issue body with task list:

```bash
# Build task list markdown
TASK_LIST=""
for CHILD in "${CHILDREN[@]}"; do
    CHILD_TITLE=$(gh issue view "$CHILD" --repo "$REPO" --json title --jq '.title')
    TASK_LIST+="- [ ] #${CHILD} ${CHILD_TITLE}\n"
done

# Update parent issue body
gh issue edit "$PARENT" --repo "$REPO" --body "$(cat <<EOF
## Context

Design doc: \`ideas/agent-controller.md\`

## Goal

<!-- Extract from design doc -->

## Constraints

<!-- Extract from design doc -->

## Sub-tasks

$TASK_LIST
EOF
)"
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
CHILDREN=()

# Helper function to create a child issue and track it
create_child() {
    local title=$1
    local body=$2

    # Create the issue
    local child_url=$(gh issue create --repo "$REPO" --title "$title" --body "$body")
    local child_number=$(echo "$child_url" | grep -oE '[0-9]+$')

    # Track for task list update
    CHILDREN+=("$child_number")

    echo "  Created #$child_number: $title"
}

# Create parent issue (initial body without task list)
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

## Sub-tasks
Will be populated below...")

PARENT=$(echo "$PARENT_URL" | grep -oE '[0-9]+$')
echo "Created parent issue #$PARENT"

# Create child issues
echo "Creating child issues..."

create_child "Create controller.sh script" "Implement polling loop, lock checking, session spawning.

## Acceptance Criteria
- [ ] Polls for agent-ready issues
- [ ] Checks/cleans stale locks
- [ ] Spawns tmux sessions
- [ ] Respects MAX_CONCURRENT limit

## Parent
See #$PARENT for full context."

create_child "Add controller Kubernetes deployment" "Create deployment manifest for controller.

## Dependencies
Work AFTER controller.sh is complete.

## Acceptance Criteria
- [ ] Deployment runs controller.sh
- [ ] Mounts repo PVC
- [ ] Has GitHub token secret

## Parent
See #$PARENT for full context."

create_child "Add controller values.yaml configuration" "Add configuration options to values.yaml.

## Acceptance Criteria
- [ ] pollInterval configurable
- [ ] lockTTL configurable
- [ ] maxConcurrent configurable
- [ ] enabled flag for opt-in

## Parent
See #$PARENT for full context."

create_child "Test end-to-end flow" "Validate the complete workflow.

## Dependencies
Work AFTER all other children complete.

## Acceptance Criteria
- [ ] Controller picks up test issue
- [ ] Claude session executes successfully
- [ ] Issue is closed on completion

## Parent
See #$PARENT for full context."

# Build task list from children
echo "Updating parent with task list..."
TASK_LIST=""
for CHILD in "${CHILDREN[@]}"; do
    CHILD_TITLE=$(gh issue view "$CHILD" --repo "$REPO" --json title --jq '.title')
    TASK_LIST+="- [ ] #${CHILD} ${CHILD_TITLE}"$'\n'
done

# Update parent issue body with task list
gh issue edit "$PARENT" --repo "$REPO" --body "## Context
Design doc: \`$DESIGN_DOC\`

## Goal
Autonomous GitHub issue execution via polling controller.

## Constraints
- Simple shell script preferred
- Must handle lock TTL
- Single controller instance

## Sub-tasks

$TASK_LIST"

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
