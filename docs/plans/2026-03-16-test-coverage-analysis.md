# Test Coverage Gap Analysis

## Commit Range
`fd80f50..812eb11` on main

## Analysis Process
1. Listed all Go/Python source files added or modified in the range (excluding tests, generated code, `__init__.py`)
2. Checked each file for a corresponding `_test` file at HEAD
3. Reviewed existing test coverage for the new behaviors introduced

## Files Reviewed

### Orchestrator (Go) — `projects/agent_platform/orchestrator/`
| File | Test File | Status |
|------|-----------|--------|
| api.go | api_test.go | ✅ Updated in same range |
| consumer.go | consumer_test.go | ✅ 136+ lines added |
| main.go | main_test.go | ✅ Covered |
| model.go | model_test.go | ✅ 298 lines added |
| result.go | result_test.go | ✅ Covered |
| sandbox.go | sandbox_test.go | ✅ 113 lines added |
| store.go | store_test.go (235 lines) | ✅ Covered |
| cmd/runner/main.go | cmd/runner/main_test.go | ✅ 212 lines added |

**Verdict:** No gaps — all orchestrator files have comprehensive test coverage.

### Ships (Python) — `projects/ships/backend/main.py`
| Behavior Changed | Test Coverage |
|-----------------|--------------|
| Read-only DB connection (`_read_db`) for API reads | ❌ Not tested |
| Position count caching (`_position_count`) tracking through inserts | ❌ Not tested |
| Position count decrement on cleanup | ❌ Not tested |
| Cache clearing on reconnect | ❌ Not tested |
| `get_vessel_count()` / `get_position_count()` changed from async→sync | ✅ Tests updated |

**Verdict:** 4 new behaviors lack test coverage. These are performance-critical (read/write separation, counter caching) and could silently regress.

## Skipped Files
- `bazel/semgrep/third_party/semgrep_pro/digests.bzl` — automated digest updates
- `bazel/tools/hooks/prefer-bb-remote.sh` — shell script
- `projects/ships/frontend/web/src/App.jsx` — JSX, not Go/Python
- All deploy config (Chart.yaml, application.yaml, values.yaml)
- `projects/agent_platform/buildbuddy_mcp/` — entirely deleted

## Pipeline Design
Only the **ships** project has gaps. One `qa-test` agent writes the tests, then `pr-review` validates.
