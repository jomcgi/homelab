# Tasks Document

- [x] 1. Create `.pre-commit-config.yaml` with core infrastructure linting hooks
  - File: `.pre-commit-config.yaml`
  - Create pre-commit configuration with yamllint, kube-linter, and detect-secrets hooks
  - Configure hook versions, file patterns, and arguments
  - Purpose: Establish foundation for YAML and Kubernetes manifest validation
  - _Leverage: None (new root configuration file)_
  - _Requirements: 1, 2, 3, 5_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: DevOps Engineer specializing in CI/CD automation and code quality tools | Task: Create `.pre-commit-config.yaml` at repository root with yamllint (for YAML syntax validation), kube-linter (for Kubernetes best practices), and detect-secrets (for secret detection) hooks following requirements 1, 2, 3, and 5. Configure appropriate versions, file patterns (\\.ya?ml$ for yamllint, Kubernetes manifests for kube-linter), and arguments (--baseline .secrets.baseline for detect-secrets). | Restrictions: Do not include Helm, Go, or Python hooks yet (separate tasks), use pinned versions (not 'latest'), ensure hooks only run on relevant file types | Leverage: Research pre-commit.com documentation for hook repository URLs and configuration syntax | Success: Configuration file is valid YAML, hooks are from official repositories with pinned versions, file patterns correctly target YAML and Kubernetes manifests, detect-secrets configured with baseline file. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [x] 2. Create `.yamllintrc` configuration file
  - File: `.yamllintrc`
  - Define yamllint rules for 2-space indentation, line length (120), and trailing whitespace
  - Configure rule exclusions for generated files or third-party charts
  - Purpose: Enforce consistent YAML formatting across repository
  - _Leverage: Project structure conventions (2-space indentation from structure.md)_
  - _Requirements: 2_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Configuration Engineer with expertise in YAML standards and linting tools | Task: Create `.yamllintrc` at repository root configuring yamllint rules following requirement 2. Set indentation to 2 spaces, line-length to 120, require 1 space from content for comments, and disable rules for overly strict checks. Use 'extends: default' as base configuration. | Restrictions: Do not set indentation to anything other than 2 spaces (project standard), do not make line-length too restrictive (<100 chars), ensure configuration matches existing YAML files in charts/ and clusters/ directories | Leverage: Review existing YAML files in charts/cloudflare-tunnel/values.yaml and clusters/homelab/ to ensure rules are compatible | Success: Configuration file is valid YAML, rules enforce 2-space indentation and 120-char line length, existing repository YAML files pass yamllint without errors. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 3. Create `.kube-linter.yaml` configuration file
  - File: `.kube-linter.yaml`
  - Configure kube-linter to enforce security best practices (non-root, read-only filesystem, no privilege escalation)
  - Enable resource limit checks and label requirements
  - Purpose: Ensure Kubernetes manifests follow homelab security principles
  - _Leverage: Security principles from CLAUDE.md and tech.md (non-root, read-only filesystem, resource limits)_
  - _Requirements: 3_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Kubernetes Security Engineer with expertise in policy enforcement and best practices | Task: Create `.kube-linter.yaml` at repository root configuring kube-linter checks following requirement 3. Enable checks: no-read-only-root-fs, run-as-non-root, no-privilege-escalation, required-label-owner (app.kubernetes.io/name), cpu-requirements, memory-requirements. Set checks to blocking (fail commit on violation). | Restrictions: Do not disable critical security checks, ensure configuration aligns with existing security patterns in charts/cloudflare-tunnel/templates/, do not add overly restrictive checks that would fail on infrastructure components (like Longhorn) | Leverage: Review existing Deployment manifests in charts/ to ensure security contexts are properly configured and will pass kube-linter checks | Success: Configuration file is valid YAML, security checks are enabled and set to blocking, existing secure manifests pass kube-linter, insecure manifests (root containers, missing resource limits) are caught. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 4. Add Helm linting hook to `.pre-commit-config.yaml`
  - File: `.pre-commit-config.yaml` (modify existing)
  - Add helm-lint hook from Gruntwork or custom script
  - Configure hook to detect Chart.yaml and run `helm lint` on modified charts
  - Purpose: Validate Helm charts for template syntax and rendering errors
  - _Leverage: Existing `.pre-commit-config.yaml` from task 1, Helm charts in charts/ directory_
  - _Requirements: 4_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Kubernetes Platform Engineer with expertise in Helm and GitOps workflows | Task: Add helm-lint hook to existing `.pre-commit-config.yaml` following requirement 4. Use Gruntwork pre-commit hook repository (https://github.com/gruntwork-io/pre-commit) with helmlint hook, or create custom local hook that detects Chart.yaml files and runs `helm lint` on parent directory. Configure hook to pass chart directory path and support linter_values.yaml if present. | Restrictions: Do not run helm lint on all charts for every commit (only modified charts), ensure Helm binary is available on PATH (add documentation note), do not hard-code chart paths | Leverage: Review existing Helm charts in charts/cloudflare-tunnel/ to understand structure and ensure hook will detect them correctly | Success: Hook is properly configured in `.pre-commit-config.yaml`, detects Helm charts by Chart.yaml presence, runs `helm lint` only on modified charts, supports linter_values.yaml merging. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 5. Create `.golangci.yml` configuration at repository root
  - File: `.golangci.yml`
  - Copy existing configuration from operators/cloudflare/.golangci.yml
  - Enhance with additional linters (gosec for security, gofumpt for stricter formatting)
  - Purpose: Enforce Go code quality and security standards across all Go projects
  - _Leverage: operators/cloudflare/.golangci.yml (existing configuration)_
  - _Requirements: 7_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Go Developer with expertise in code quality tools and static analysis | Task: Create `.golangci.yml` at repository root following requirement 7. Start by copying configuration from operators/cloudflare/.golangci.yml, then add gosec linter for security checks (hardcoded credentials, SQL injection, weak crypto). Keep all existing linters (copyloopvar, errcheck, govet, staticcheck, revive, etc.) and formatters (gofmt, goimports). Set timeout to 5m and allow-parallel-runners: true. | Restrictions: Do not remove existing linters from operators/cloudflare/.golangci.yml, do not add overly strict linters that would fail on existing code without good reason, ensure configuration works with both operator code and future Go utilities | Leverage: Read operators/cloudflare/.golangci.yml and operators/cloudflare/internal/ Go code to understand existing patterns and ensure new linters are compatible | Success: Configuration file is valid YAML v2 format, includes all linters from existing config plus gosec, formatters are enabled (gofmt, goimports), configuration works with existing Go code in operators/cloudflare/. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 6. Add Go linting hooks to `.pre-commit-config.yaml`
  - File: `.pre-commit-config.yaml` (modify existing)
  - Add golangci-lint hook from official repository
  - Configure hook to run only on *.go files with --fix flag
  - Purpose: Automatically lint and format Go code on commit
  - _Leverage: Existing `.pre-commit-config.yaml`, `.golangci.yml` from task 5_
  - _Requirements: 7_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Go DevOps Engineer with expertise in automation and linting workflows | Task: Add golangci-lint hook to `.pre-commit-config.yaml` following requirement 7. Use official golangci-lint pre-commit repository (https://github.com/golangci/golangci-lint), hook ID 'golangci-lint', configure to run on files matching '\\.go$', pass arguments ['--fix'] for auto-fixing, and set pass_filenames: true to only lint changed files. | Restrictions: Do not use golangci-lint-full hook (too slow for pre-commit), do not run on all files (only changed .go files), ensure hook uses .golangci.yml configuration from repository root | Leverage: Review golangci-lint pre-commit hook documentation and test with existing Go code in operators/cloudflare/ | Success: Hook is properly added to `.pre-commit-config.yaml`, runs golangci-lint on .go files only with --fix flag, uses .golangci.yml configuration, existing Go code passes linting. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 7. Create `pyproject.toml` with Ruff configuration
  - File: `pyproject.toml`
  - Configure Ruff for Python linting and formatting
  - Set line-length to 120, target-version to py38, enable security and style rules
  - Purpose: Enforce modern Python code quality standards
  - _Leverage: None (new configuration, no existing Python code)_
  - _Requirements: 8_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Python Developer with expertise in code quality tools and modern linting practices | Task: Create `pyproject.toml` at repository root with Ruff configuration following requirement 8. Set [tool.ruff] line-length=120, target-version="py38". Configure [tool.ruff.lint] with select rules: E (pycodestyle errors), W (warnings), F (Pyflakes), I (isort), N (pep8-naming), S (bandit security), B (bugbear), UP (pyupgrade), C4 (comprehensions). Add [tool.ruff.lint.per-file-ignores] with "tests/*" = ["S101"] to allow assert in tests. | Restrictions: Do not set line-length below 100 (too restrictive) or above 120, do not enable rules that conflict with Black compatibility, ensure target-version matches minimum Python version for project | Leverage: Review Ruff documentation for 2025 best practices and default rule configurations | Success: Configuration file is valid TOML, Ruff linting rules enforce security and style, line-length is 120, per-file-ignores allow asserts in tests. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 8. Add Python linting hooks to `.pre-commit-config.yaml`
  - File: `.pre-commit-config.yaml` (modify existing)
  - Add ruff and ruff-format hooks from official ruff-pre-commit repository
  - Configure ruff hook to run before ruff-format with --fix flag
  - Purpose: Automatically lint and format Python code on commit
  - _Leverage: Existing `.pre-commit-config.yaml`, `pyproject.toml` from task 7_
  - _Requirements: 8_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Python DevOps Engineer with expertise in modern Python tooling and pre-commit workflows | Task: Add Ruff hooks to `.pre-commit-config.yaml` following requirement 8. Use official ruff-pre-commit repository (https://github.com/astral-sh/ruff-pre-commit), add two hooks in order: (1) 'ruff' with args: ['--fix'] for linting, (2) 'ruff-format' for formatting. Both hooks run on files matching '\\.py$'. Ensure ruff hook runs before ruff-format (critical ordering requirement). | Restrictions: Do not reverse hook order (ruff must run before ruff-format), do not skip --fix flag for ruff (needed for auto-fixes), ensure hooks use pyproject.toml configuration from repository root | Leverage: Review Ruff pre-commit documentation and test ordering requirements to ensure lint fixes don't conflict with formatting | Success: Both hooks properly added to `.pre-commit-config.yaml`, ruff runs before ruff-format, hooks use pyproject.toml configuration, Python code is linted and formatted correctly. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 9. Add Checkov compliance hook to `.pre-commit-config.yaml`
  - File: `.pre-commit-config.yaml` (modify existing)
  - Add checkov hook for Kubernetes compliance validation
  - Configure to run on Kubernetes YAML files with framework filter
  - Purpose: Validate Kubernetes manifests against CIS benchmarks
  - _Leverage: Existing `.pre-commit-config.yaml`, Kubernetes manifests in charts/ and clusters/_
  - _Requirements: 6_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Security Compliance Engineer with expertise in Kubernetes security policies and CIS benchmarks | Task: Add Checkov hook to `.pre-commit-config.yaml` following requirement 6. Use official Checkov pre-commit repository (https://github.com/bridgecrewio/checkov), hook ID 'checkov', configure args: ['--framework', 'kubernetes'] to only run Kubernetes checks. Set files pattern to match Kubernetes YAML manifests (charts/.*/templates/.*\\.yaml$ and clusters/.*\\.yaml$). | Restrictions: Do not run Checkov on all YAML files (too slow), limit to Kubernetes manifests only, do not add skip-check for critical security violations, ensure blocking security checks fail commit | Leverage: Review existing Kubernetes manifests in charts/cloudflare-tunnel/templates/ and ensure they pass Checkov CIS benchmark checks | Success: Hook is properly added to `.pre-commit-config.yaml`, runs on Kubernetes manifests only, validates against CIS benchmarks, critical security violations block commit. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 10. Initialize detect-secrets baseline file
  - File: `.secrets.baseline`
  - Run `detect-secrets scan --baseline .secrets.baseline` to create initial baseline
  - Audit baseline to approve any existing false positives
  - Purpose: Establish baseline for secret detection and manage false positives
  - _Leverage: `.pre-commit-config.yaml` with detect-secrets hook from task 1_
  - _Requirements: 5_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Security Engineer with expertise in secret management and false positive analysis | Task: Create `.secrets.baseline` file following requirement 5 by running `detect-secrets scan --baseline .secrets.baseline` from repository root. Review generated baseline with `detect-secrets audit .secrets.baseline` and mark any false positives (example UUIDs, OnePasswordItem references, documentation examples) as approved. Ensure real secrets (if any) are NOT marked as false positives. | Restrictions: Do not mark actual secrets as false positives, do not skip auditing process, ensure baseline is committed to repository, verify OnePasswordItem CRD references are allowed (not plaintext secrets) | Leverage: Review files flagged by detect-secrets scan and verify they are truly false positives by checking context (example values, CRD references, test fixtures) | Success: Baseline file is created and committed, false positives are properly marked, real secrets (if any) are removed before baseline creation, detect-secrets hook passes on existing repository files. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 11. Add Claude Code hook integration to `.claude/settings.json`
  - File: `.claude/settings.json` (modify existing)
  - Add PostToolUse hook for Edit/Write tools to run pre-commit validation
  - Add PreToolUse hook for git commit to run full pre-commit check
  - Purpose: Integrate pre-commit validation into Claude Code workflow
  - _Leverage: Existing `.claude/settings.json` with permissions and MCP server config_
  - _Requirements: 9_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Claude Code Integration Engineer with expertise in hook configuration and automation workflows | Task: Add pre-commit hook integrations to `.claude/settings.json` following requirement 9. Add "hooks" section with two entries: (1) PostToolUse hook matching "Edit|Write" tools that runs "pre-commit run --files $FILE_PATH || true" (non-blocking), (2) PreToolUse hook matching "Bash(git commit:*)" that runs "pre-commit run --all-files" (blocking). Preserve existing env, permissions, and MCP server configurations. | Restrictions: Do not remove existing permissions or MCP server settings, ensure PostToolUse hook is non-blocking (|| true) so Claude can see errors but continue, ensure PreToolUse hook is blocking (no || true) to prevent commits with violations, use correct file path variable for PostToolUse | Leverage: Review Claude Code hooks documentation and existing .claude/settings.json structure to ensure proper JSON syntax and hook configuration | Success: Hooks are properly added to `.claude/settings.json`, JSON is valid, PostToolUse hook runs pre-commit on edited files (non-blocking), PreToolUse hook blocks git commit if validation fails. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 12. Update root README.md with pre-commit setup documentation
  - File: `README.md` (modify existing)
  - Add "Pre-commit Linting" section with installation and usage instructions
  - Document how to bypass hooks in emergencies and where to find rule documentation
  - Purpose: Provide clear setup instructions for new developers
  - _Leverage: Existing README.md structure, documentation standards from structure.md_
  - _Requirements: 11_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: Technical Documentation Writer with expertise in developer onboarding and tool documentation | Task: Add comprehensive pre-commit linting section to README.md following requirement 11. Include: (1) Installation steps: "pip install pre-commit && pre-commit install", (2) Usage: hooks run automatically on git commit, (3) Manual run: "pre-commit run --all-files", (4) Emergency bypass: "git commit --no-verify" (with warning that CI still validates), (5) Links to configuration files and rule documentation (yamllint, kube-linter, golangci-lint, Ruff, Checkov). Add section after "Development Workflow" or in appropriate location. | Restrictions: Do not remove existing README content, ensure instructions are clear and concise, include warning about bypassing hooks, link to relevant tool documentation for detailed rule explanations | Leverage: Review existing README.md structure and tone, review structure.md documentation standards for appropriate detail level and formatting | Success: README.md has clear pre-commit section with installation, usage, and bypass instructions, links to tool documentation are included, instructions are accurate and tested. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 13. Test complete pre-commit workflow end-to-end
  - Files: All configuration files, test with sample violations
  - Run `pre-commit install` and test all hooks with sample files containing violations
  - Verify hooks catch violations (YAML syntax, K8s security, secrets, Go/Python issues)
  - Purpose: Ensure complete pre-commit system works correctly and catches all violation types
  - _Leverage: All configuration files from previous tasks_
  - _Requirements: All (integration test)_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: QA Engineer with expertise in integration testing and end-to-end validation | Task: Perform comprehensive end-to-end testing of complete pre-commit system covering all requirements. Test procedure: (1) Run "pre-commit install", (2) Create test files with violations: YAML with wrong indentation, Kubernetes Deployment with root container and no resource limits, Helm chart with invalid template syntax, Go file with unused variable, Python file with unused import and wrong formatting, file with fake API key. (3) Run "git commit" on each file type and verify hook catches violation with clear error message. (4) Fix violations and verify hooks pass. (5) Run "pre-commit run --all-files" and measure execution time (<60s requirement). (6) Test Claude Code integration by editing file with violation via Claude Code and verify PostToolUse hook reports error. | Restrictions: Do not skip any hook testing, ensure all violation types are tested, verify error messages are clear and actionable, test both failure and success cases | Leverage: Use operators/cloudflare/ for Go testing, create temporary test files in appropriate directories, review design.md error handling section for expected error formats | Success: All hooks execute correctly, violations are caught with clear error messages, fixes allow commits to proceed, performance meets requirements (<10s single file, <60s all files), Claude Code integration works as expected. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._

- [ ] 14. Create GitHub Actions workflow for CI validation (optional future task)
  - File: `.github/workflows/pre-commit.yml`
  - Create GitHub Actions workflow that runs `pre-commit run --all-files` on PRs
  - Configure workflow to fail PR if any hook fails
  - Purpose: Ensure commits bypassing local hooks are still validated in CI
  - _Leverage: Existing `.pre-commit-config.yaml`, GitHub Actions setup patterns_
  - _Requirements: 12_
  - _Prompt: Implement the task for spec pre-commit-linting, first run spec-workflow-guide to get the workflow guide then implement the task: Role: CI/CD Engineer with expertise in GitHub Actions and automated testing pipelines | Task: Create `.github/workflows/pre-commit.yml` workflow following requirement 12. Configure workflow to: (1) Trigger on pull_request events, (2) Set up Python environment with actions/setup-python@v4, (3) Install pre-commit with "pip install pre-commit", (4) Run "pre-commit run --all-files", (5) Fail workflow if any hook fails (default behavior). Use ubuntu-latest runner. | Restrictions: Do not add complex caching yet (can be optimized later), ensure workflow uses same .pre-commit-config.yaml as local development, do not skip any hooks in CI | Leverage: Review GitHub Actions documentation and existing workflow patterns from other repositories, ensure golangci-lint-full is not used (too slow) | Success: Workflow file is valid GitHub Actions YAML, triggers on pull requests, runs all pre-commit hooks, fails PR if violations found, uses consistent configuration with local development. After implementation, mark task as in-progress in tasks.md before starting, then mark as complete [x] when done._
