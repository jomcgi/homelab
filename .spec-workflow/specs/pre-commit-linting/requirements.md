# Requirements Document

## Introduction

This specification defines a comprehensive pre-commit linting system for the homelab Kubernetes infrastructure repository. The system will enforce industry best practices for YAML, Kubernetes manifests, Helm charts, Go, and Python code before code is committed, ensuring code quality, security compliance, and operational reliability. Additionally, it will expose these hooks to Claude Code to enable automated validation during AI-assisted development.

## Alignment with Product Vision

This feature directly supports the product principles outlined in product.md:

- **Simplicity over Cleverness**: Automated linting catches common mistakes early, preventing complex debugging later
- **Security by Default**: Linting rules enforce security best practices (non-root containers, resource limits, code vulnerabilities)
- **Observable Everything**: Linting ensures all services export proper health checks and metrics endpoints
- **Obvious Code**: Consistent formatting and style make the codebase easier to understand

By catching issues at commit time, we reduce the "Time to Deploy New Service" metric and improve "Deployment Success Rate" by preventing malformed configurations from entering the repository.

## Requirements

### Requirement 1: Pre-commit Framework Integration

**User Story:** As a homelab operator, I want pre-commit hooks automatically installed and configured, so that I don't have to manually run linting tools before every commit.

#### Acceptance Criteria

1. WHEN the repository is cloned THEN the developer SHALL be able to run `pre-commit install` to configure Git hooks
2. WHEN a developer runs `git commit` THEN the pre-commit framework SHALL automatically execute all configured linting hooks
3. IF any hook fails THEN the commit SHALL be blocked AND the developer SHALL receive clear error messages with file names and line numbers
4. WHEN all hooks pass THEN the commit SHALL proceed normally

### Requirement 2: YAML Syntax and Style Validation

**User Story:** As a homelab operator, I want all YAML files automatically validated for syntax and formatting, so that I don't introduce parsing errors or inconsistent formatting.

#### Acceptance Criteria

1. WHEN any YAML file is modified THEN yamllint SHALL validate syntax and formatting rules
2. WHEN yamllint detects errors THEN it SHALL report the file path, line number, and specific rule violation
3. IF a YAML file has incorrect indentation THEN the commit SHALL be blocked
4. WHEN YAML files follow the configured rules (2-space indentation, no trailing whitespace) THEN yamllint SHALL pass
5. IF a YAML file contains duplicate keys THEN yamllint SHALL detect and report the error

### Requirement 3: Kubernetes Manifest Best Practices Validation

**User Story:** As a homelab operator, I want Kubernetes manifests validated against best practices and security policies, so that I don't deploy insecure or poorly configured workloads.

#### Acceptance Criteria

1. WHEN any Kubernetes manifest is modified THEN kube-linter SHALL validate against best practices
2. WHEN a Deployment lacks resource limits THEN kube-linter SHALL fail the commit with a specific error
3. WHEN a container runs as root THEN kube-linter SHALL fail the commit with a security warning
4. WHEN a container has `allowPrivilegeEscalation: true` THEN kube-linter SHALL fail the commit
5. IF a Service or Deployment is missing required labels (app.kubernetes.io/name) THEN kube-linter SHALL report a warning
6. WHEN all security and best practice rules pass THEN kube-linter SHALL allow the commit

### Requirement 4: Helm Chart Validation

**User Story:** As a homelab operator, I want Helm charts automatically validated for syntax and template errors, so that I don't deploy broken charts to the cluster.

#### Acceptance Criteria

1. WHEN any file in a Helm chart is modified THEN `helm lint` SHALL validate the entire chart
2. WHEN a Helm template contains invalid Go template syntax THEN `helm lint` SHALL fail with a descriptive error
3. WHEN required values are missing in values.yaml THEN `helm lint` SHALL detect the issue (using linter_values.yaml if needed)
4. WHEN a chart has invalid Chart.yaml metadata THEN `helm lint` SHALL report the error
5. IF templates render correctly with default values THEN `helm lint` SHALL pass

### Requirement 5: Security and Secrets Detection

**User Story:** As a homelab operator, I want to prevent accidental commits of secrets or sensitive data, so that I don't expose credentials in Git history.

#### Acceptance Criteria

1. WHEN any file is committed THEN detect-secrets SHALL scan for potential secrets
2. WHEN high-entropy strings resembling API keys are detected THEN the commit SHALL be blocked
3. WHEN patterns matching common secret formats (AWS keys, private keys) are found THEN detect-secrets SHALL fail
4. IF a file contains a 1Password OnePasswordItem reference THEN detect-secrets SHALL allow it (not a plaintext secret)
5. WHEN a false positive is detected THEN the developer SHALL be able to add it to a baseline file to allow the commit

### Requirement 6: Compliance and Policy Validation

**User Story:** As a homelab operator, I want Kubernetes manifests validated against security compliance policies, so that I maintain a strong security posture.

#### Acceptance Criteria

1. WHEN any Kubernetes manifest is modified THEN Checkov SHALL validate against CIS Kubernetes benchmarks
2. WHEN a container has a writable root filesystem THEN Checkov SHALL fail the commit
3. WHEN securityContext is missing from a Pod spec THEN Checkov SHALL report a violation
4. WHEN NetworkPolicies are required but missing THEN Checkov SHALL provide a warning (not blocking)
5. IF all compliance checks pass THEN Checkov SHALL allow the commit

### Requirement 7: Go Code Linting and Formatting

**User Story:** As a homelab operator writing Go code for operators or utilities, I want my Go code automatically formatted and linted, so that it follows Go best practices and is consistent.

#### Acceptance Criteria

1. WHEN any Go file is modified THEN gofmt SHALL automatically format the code
2. WHEN Go imports are out of order or unused THEN goimports SHALL organize and clean them
3. WHEN any Go file is modified THEN golangci-lint SHALL run comprehensive linting checks
4. WHEN golangci-lint detects issues (code smells, potential bugs, style violations) THEN the commit SHALL be blocked with specific errors
5. IF golangci-lint can auto-fix issues THEN it SHALL apply fixes with `--fix` flag
6. WHEN Go code passes all linting rules THEN the commit SHALL proceed
7. IF a .golangci.yml configuration exists THEN golangci-lint SHALL use those custom rules

### Requirement 8: Python Code Linting and Formatting

**User Story:** As a homelab operator writing Python scripts or operators, I want my Python code automatically formatted and linted, so that it follows modern Python best practices.

#### Acceptance Criteria

1. WHEN any Python file is modified THEN Ruff SHALL run linting checks
2. WHEN Ruff detects fixable issues THEN it SHALL auto-fix them with `--fix` flag
3. WHEN any Python file is modified THEN Ruff formatter SHALL format the code
4. WHEN Python code has style violations, unused imports, or code smells THEN Ruff SHALL report specific errors
5. IF a pyproject.toml configuration exists THEN Ruff SHALL use those custom rules
6. WHEN Ruff linting is configured THEN it SHALL run before Ruff formatting
7. WHEN Python code passes all Ruff checks THEN the commit SHALL proceed
8. IF type checking is required THEN mypy SHALL validate type annotations (optional, can be added later)

### Requirement 9: Claude Code Hook Integration

**User Story:** As a homelab operator using Claude Code, I want the AI assistant to automatically validate changes using pre-commit hooks, so that I catch issues before manually committing.

#### Acceptance Criteria

1. WHEN Claude Code is configured in the project THEN a `.claude/settings.json` file SHALL define pre-commit hook integrations
2. WHEN Claude Code executes an Edit or Write tool THEN a PostToolUse hook SHALL trigger pre-commit validation on modified files
3. IF validation fails THEN Claude Code SHALL receive the error output and report it to the user
4. WHEN validation passes THEN Claude Code SHALL continue normally without blocking
5. WHEN a user runs `git commit` via Claude Code THEN a PreToolUse hook SHALL trigger `pre-commit run --all-files` before the commit

### Requirement 10: Fast Feedback and Performance

**User Story:** As a homelab operator, I want linting to complete quickly, so that my development workflow is not significantly slowed down.

#### Acceptance Criteria

1. WHEN committing a single file change THEN all linting hooks SHALL complete in under 10 seconds
2. WHEN running `pre-commit run --all-files` on the entire repository THEN it SHALL complete in under 60 seconds
3. IF a linting tool takes longer than 30 seconds THEN it SHALL provide progress output
4. WHEN only specific file types are changed THEN only relevant hooks SHALL run (e.g., YAML linter skips non-YAML files)
5. WHEN Go code is changed THEN golangci-lint SHALL only run on modified files (not entire module)
6. WHEN Python code is changed THEN Ruff SHALL leverage its Rust-based performance (200x faster than traditional tools)

### Requirement 11: Developer Experience and Documentation

**User Story:** As a new contributor to the homelab, I want clear documentation on setting up and using pre-commit hooks, so that I can quickly get started.

#### Acceptance Criteria

1. WHEN a developer clones the repository THEN the root README.md SHALL include setup instructions for pre-commit
2. WHEN a hook fails THEN the error message SHALL include a link to documentation explaining the rule
3. IF a developer needs to bypass a hook (emergency fix) THEN they SHALL be able to use `git commit --no-verify` with documented warnings
4. WHEN pre-commit is not installed THEN running `pre-commit install` SHALL provide a helpful error message with installation instructions
5. WHEN developers need to understand Go linting rules THEN documentation SHALL link to golangci-lint configuration
6. WHEN developers need to understand Python linting rules THEN documentation SHALL link to Ruff configuration

### Requirement 12: CI/CD Integration

**User Story:** As a homelab operator, I want the same linting checks to run in CI/CD, so that commits bypassing hooks are still validated.

#### Acceptance Criteria

1. WHEN a pull request is created THEN GitHub Actions SHALL run `pre-commit run --all-files`
2. IF any hook fails in CI THEN the PR SHALL be marked as failing
3. WHEN CI runs pre-commit THEN it SHALL use the exact same configuration as local development
4. IF CI passes but local hooks fail THEN the configurations SHALL be synchronized
5. WHEN CI runs Go linting THEN it SHALL use golangci-lint-full (runs on all files, not just changed)

## Non-Functional Requirements

### Code Architecture and Modularity
- **Single Responsibility Principle**: Each hook configuration targets a specific validation concern (YAML syntax, Kubernetes security, Helm linting, Go formatting, Python linting)
- **Modular Design**: Hooks are independently configurable and can be enabled/disabled without affecting others
- **Dependency Management**: Pre-commit framework manages tool versions and dependencies in isolated environments
- **Clear Interfaces**: `.pre-commit-config.yaml` serves as the single source of truth for hook configuration

### Performance
- Linting tools must complete within seconds, not minutes, to maintain development velocity
- Only modified files should be checked (pre-commit's default behavior)
- Caching should be used where possible to speed up repeated runs
- Yamllint should scan 100+ files in under 5 seconds (based on 2025 benchmarks)
- Ruff should leverage its Rust-based performance for Python (200x faster than traditional tools)
- golangci-lint should only run on changed files in pre-commit, full repo in CI

### Security
- Secrets must never be committed to the repository
- All linting tools must be from trusted, well-maintained sources (official pre-commit repos or verified third-party hooks)
- Hook execution must not expose sensitive environment variables or credentials
- False positives in secret detection should be minimized while maintaining high sensitivity
- Go and Python security linters should detect potential vulnerabilities (SQL injection, hardcoded credentials, etc.)

### Reliability
- Pre-commit hooks must work consistently across different operating systems (macOS, Linux)
- Hook failures must provide actionable error messages, not cryptic tool output
- If a linting tool is unavailable or fails to install, pre-commit should provide clear guidance
- The system must handle large files and repositories gracefully
- Go module structure should be correctly detected by golangci-lint
- Python environments should be isolated to prevent dependency conflicts

### Usability
- Setup should require minimal steps: `pip install pre-commit && pre-commit install`
- Error messages should be developer-friendly with file paths, line numbers, and suggested fixes
- Hooks should auto-fix issues where possible (e.g., trailing whitespace removal, Go imports, Python formatting)
- Documentation should include examples of common violations and how to fix them
- Configuration files (.golangci.yml, pyproject.toml) should have sensible defaults that align with homelab security principles
