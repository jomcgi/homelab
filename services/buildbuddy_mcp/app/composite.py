"""Composite BuildBuddy MCP tools that orchestrate multiple API calls."""

from __future__ import annotations

from services.buildbuddy_mcp.app.main import (
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
    mcp,
)


def _find_test_invocation(invocations: list[dict]) -> dict | None:
    """Find the inner bazel test invocation from a list of invocations."""
    for inv in invocations:
        if inv.get("command") == "test":
            return inv
    return None


@mcp.tool
async def diagnose_failure(
    invocation_id: str | None = None,
    commit_sha: str | None = None,
) -> dict:
    """One-shot CI failure diagnosis.

    Given a workflow invocation ID or commit SHA, finds failed tests,
    retrieves their test logs, and extracts error lines from the build
    log. Returns everything needed to understand a CI failure in a
    single tool call.
    """
    # Step 1: Get the invocation with child invocations
    inv_result = await get_invocation(
        invocation_id=invocation_id,
        commit_sha=commit_sha,
        include_child_invocations=True,
    )
    if "error" in inv_result:
        return inv_result
    invocations = inv_result.get("invocation", [])
    if not invocations:
        return {"error": "No invocation found"}

    # Find the workflow invocation and its children
    workflow_inv = invocations[0]
    child_ids = [
        c.get("invocation_id") or c.get("invocationId")
        for c in workflow_inv.get(
            "child_invocations", workflow_inv.get("childInvocations", [])
        )
    ]

    # Step 2: Find the inner test invocation
    test_inv_id = None
    if child_ids:
        for child_id in child_ids:
            child_result = await get_invocation(invocation_id=child_id)
            if "error" not in child_result:
                for inv in child_result.get("invocation", []):
                    if inv.get("command") == "test":
                        test_inv_id = inv["id"].get("invocation_id") or inv["id"].get(
                            "invocationId"
                        )
                        break
            if test_inv_id:
                break

    target_inv_id = test_inv_id or (
        workflow_inv["id"].get("invocation_id")
        or workflow_inv["id"].get("invocationId")
    )

    # Step 3: Get failed targets
    target_result = await get_target(invocation_id=target_inv_id, status="FAILED")
    failed_targets = target_result.get("target", [])

    # Step 4: For each failed target, get test logs
    enriched_targets = []
    for target in failed_targets:
        target_label = target.get("label", "")
        entry = {
            "label": target_label,
            "status": target.get("status"),
            "timing": target.get("timing"),
            "test_log": None,
        }

        action_result = await get_action(
            invocation_id=target_inv_id,
            target_label=target_label,
        )
        for action in action_result.get("action", []):
            for f in action.get("file", []):
                if f.get("name") == "test.log" and f.get("uri"):
                    file_result = await get_file(uri=f["uri"])
                    if "contents" in file_result:
                        entry["test_log"] = file_result["contents"]
                    break
            if entry["test_log"]:
                break

        enriched_targets.append(entry)

    # Step 5: Get error lines from build log
    log_result = await get_log(invocation_id=target_inv_id, errors_only=True)
    build_errors = log_result.get("log", {}).get("contents", "")

    total_targets = target_result.get("_total_before_filter", len(failed_targets))
    status = "FAILED" if failed_targets else "SUCCESS"
    summary = (
        f"{len(failed_targets)} of {total_targets} targets failed"
        if failed_targets
        else "All targets passed"
    )

    return {
        "invocation_id": target_inv_id,
        "status": status,
        "summary": summary,
        "failed_targets": enriched_targets,
        "build_errors": build_errors,
    }
