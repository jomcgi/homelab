# CI Failure Runbook

## Failure Information

### Job Details

- **Job Name**: [GitHub Actions job name]
- **Workflow**: [Workflow file name]
- **Branch**: [Branch where failure occurred]
- **Commit**: [Commit SHA]
- **PR Number**: [If applicable]

### Failure Type

- [ ] Build failure
- [ ] Test failure
- [ ] Lint/Format failure
- [ ] Dependency resolution failure
- [ ] Container build failure
- [ ] Deployment/Sync failure
- [ ] Timeout

## Accessing Logs

### GitHub Actions Logs

```
1. Navigate to the PR or commit
2. Click on "Checks" tab or status icon
3. Click on the failed job
4. Expand the failed step to view logs
```

### BuildBuddy Logs (for Bazel builds)

```
1. Find the BuildBuddy invocation link in the GitHub Actions log
2. Or navigate to https://app.buildbuddy.io
3. Look for the invocation ID in the job output
4. In BuildBuddy, examine:
   - [ ] Build timeline
   - [ ] Target/action failures
   - [ ] Cache statistics
   - [ ] Remote execution logs
```

### Invocation URL Pattern

```
https://app.buildbuddy.io/invocation/[invocation-id]
```

## Common CI Failure Causes

### Build Failures

- [ ] **Syntax error** - Code doesn't compile
- [ ] **Missing dependency** - Import not found
- [ ] **Type error** - Type mismatch in typed languages
- [ ] **Bazel BUILD file error** - Incorrect target definition
- [ ] **Missing generated files** - Forgot to run gazelle/codegen

### Test Failures

- [ ] **Flaky test** - Passes locally, fails in CI
- [ ] **Environment difference** - CI environment differs from local
- [ ] **Race condition** - Timing-dependent failure
- [ ] **Missing test data** - Test fixtures not available
- [ ] **Resource exhaustion** - Test needs more memory/CPU

### Dependency Issues

- [ ] **Lock file mismatch** - pnpm-lock.yaml, uv.lock, or go.sum out of sync
- [ ] **Version conflict** - Incompatible package versions
- [ ] **Registry unavailable** - npm/PyPI/Go proxy down
- [ ] **Private package access** - Auth issues for private repos

### Container Build Issues

- [ ] **Base image unavailable** - Registry pull failure
- [ ] **apko build failure** - Invalid apko configuration
- [ ] **Layer size** - Image exceeds size limits
- [ ] **Multi-arch failure** - ARM/AMD64 build mismatch

### Resource/Timeout Issues

- [ ] **Memory limit** - Job OOMKilled
- [ ] **CPU limit** - Build too slow
- [ ] **Network timeout** - External service unreachable
- [ ] **Cache miss** - Full rebuild taking too long

## Debug Steps

### Step 1: Identify the Failure Point

```
1. Scroll to the end of the failed step output
2. Look for error messages, stack traces, or exit codes
3. Note the exact file and line number if provided
```

### Step 2: Reproduce Locally

```bash
# For Bazel builds
bazel build //path/to:target

# For specific tests
bazel test //path/to:test_target --test_output=all

# For lint/format checks
format  # or run pre-commit hooks manually
```

### Step 3: Check for Known Issues

- [ ] Is this a known flaky test?
- [ ] Has CI been failing on main branch?
- [ ] Are there infrastructure issues (check status pages)?

### Step 4: Examine BuildBuddy Details

```
In BuildBuddy invocation:
1. Click on "Targets" to see which targets failed
2. Click on failed target for detailed logs
3. Check "Timing" tab for performance issues
4. Check "Cache" tab for cache hit rates
5. Check "Artifacts" for test logs and outputs
```

## Fix and Verification Steps

### For Build Errors

1. Fix the code/configuration locally
2. Run the same build command locally
3. Commit and push to trigger CI

### For Test Failures

1. Run the failing test locally with verbose output:
   ```bash
   bazel test //path/to:test --test_output=all --test_arg=-v
   ```
2. If flaky, check for:
   - Timeouts that need adjustment
   - Race conditions in concurrent tests
   - External service dependencies
3. Fix and verify with multiple runs:
   ```bash
   bazel test //path/to:test --runs_per_test=5
   ```

### For Dependency Issues

1. Regenerate lock files:
   ```bash
   # For Python (uv)
   uv lock

   # For Node.js (pnpm)
   pnpm install

   # For Go
   go mod tidy
   ```
2. For Bazel deps, regenerate with gazelle:
   ```bash
   bazel run //:gazelle
   ```

### For Format/Lint Failures

1. Run the format command:
   ```bash
   format
   ```
2. Check for files that need manual fixes
3. Commit the formatted changes

## Verification Checklist

- [ ] Fix applied and committed
- [ ] CI job now passes
- [ ] No new warnings introduced
- [ ] Related tests still passing
- [ ] PR updated with fix explanation

## Escalation

| Issue Type | Contact | Notes |
|------------|---------|-------|
| Flaky tests | Test owner | Check git blame for test file |
| Build infra | Platform team | BuildBuddy or GitHub Actions issues |
| Dependency | Package maintainer | External package problems |

## Related Resources

- **BuildBuddy Dashboard**: https://app.buildbuddy.io
- **GitHub Actions Docs**: https://docs.github.com/en/actions
- **Bazel Troubleshooting**: [Link to internal docs]
- **CI Configuration**: `.github/workflows/`
