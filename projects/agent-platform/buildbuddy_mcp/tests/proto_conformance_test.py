"""Proto conformance tests — validates our tool parameters match BuildBuddy's API.

Tagged 'external' because it fetches proto files from GitHub at test time.
Run manually: bazel test //projects/agent-platform/buildbuddy_mcp/tests:proto_conformance_test
Excluded from CI via --test_tag_filters=-external.
"""

from __future__ import annotations

import inspect
import re

import httpx
import pytest

from buildbuddy_mcp.app.main import (
    execute_workflow,
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
    run,
)

PROTO_BASE = (
    "https://raw.githubusercontent.com/buildbuddy-io/buildbuddy/master/proto/api/v1"
)

# Parameters we add client-side that don't exist in the proto
CLIENT_SIDE_PARAMS = {
    "get_target": {"status"},
    "get_log": {"errors_only"},
    "get_invocation": {
        "include_child_invocations",
        "include_metadata",
        "include_artifacts",
    },
    "execute_workflow": {"run_async", "env", "visibility", "disable_retry"},
    "run": {"repo_url", "steps", "env", "timeout", "wait_until"},
}

# Map our function params to proto field names (when they differ)
PARAM_TO_PROTO = {
    "run_async": "async",
    "repo_url": "repo_url",
}


def _fetch_proto(filename: str) -> str:
    """Fetch a proto file from BuildBuddy's GitHub repo."""
    resp = httpx.get(f"{PROTO_BASE}/{filename}", timeout=30)
    resp.raise_for_status()
    return resp.text


def _parse_selector_fields(proto_text: str, message_name: str) -> set[str]:
    """Extract field names from a protobuf message definition."""
    pattern = rf"message {message_name}\s*\{{([^}}]+)\}}"
    match = re.search(pattern, proto_text, re.DOTALL)
    if not match:
        return set()
    body = match.group(1)
    # Match field definitions: type name = N;
    fields = re.findall(r"(?:repeated\s+)?\w+\s+(\w+)\s*=\s*\d+", body)
    return set(fields)


def _get_tool_params(func) -> set[str]:
    """Get parameter names from a tool function, excluding 'self'."""
    sig = inspect.signature(func)
    return {p for p in sig.parameters if p != "self"}


def _snake_to_proto(name: str) -> str:
    """Our params are already snake_case matching proto convention."""
    return PARAM_TO_PROTO.get(name, name)


class TestTargetProtoConformance:
    @pytest.fixture(autouse=True)
    def _fetch(self):
        self.proto = _fetch_proto("target.proto")

    def test_selector_fields_covered(self):
        proto_fields = _parse_selector_fields(self.proto, "TargetSelector")
        our_params = _get_tool_params(get_target)
        client_side = CLIENT_SIDE_PARAMS.get("get_target", set())

        # Every proto selector field should be a parameter on our tool
        for field in proto_fields:
            assert field in our_params or field in {"invocation_id"}, (
                f"Proto field '{field}' in TargetSelector not exposed in get_target. "
                f"Our params: {our_params}"
            )

        # Every non-client-side param should map to a proto field or standard param
        standard = {"page_token", "invocation_id"}
        for param in our_params - client_side - standard:
            proto_name = _snake_to_proto(param)
            assert proto_name in proto_fields, (
                f"Tool param '{param}' not in TargetSelector proto. "
                f"Proto fields: {proto_fields}. "
                f"If this is intentional, add to CLIENT_SIDE_PARAMS."
            )


class TestActionProtoConformance:
    @pytest.fixture(autouse=True)
    def _fetch(self):
        self.proto = _fetch_proto("action.proto")

    def test_selector_fields_covered(self):
        proto_fields = _parse_selector_fields(self.proto, "ActionSelector")
        our_params = _get_tool_params(get_action)
        client_side = CLIENT_SIDE_PARAMS.get("get_action", set())

        for field in proto_fields:
            assert field in our_params or field in {"invocation_id"}, (
                f"Proto field '{field}' in ActionSelector not exposed in get_action. "
                f"Our params: {our_params}"
            )

        standard = {"page_token", "invocation_id"}
        for param in our_params - client_side - standard:
            proto_name = _snake_to_proto(param)
            assert proto_name in proto_fields, (
                f"Tool param '{param}' not in ActionSelector proto. "
                f"Proto fields: {proto_fields}"
            )


class TestFileProtoConformance:
    @pytest.fixture(autouse=True)
    def _fetch(self):
        self.proto = _fetch_proto("file.proto")

    def test_request_fields_covered(self):
        proto_fields = _parse_selector_fields(self.proto, "GetFileRequest")
        our_params = _get_tool_params(get_file)
        client_side = CLIENT_SIDE_PARAMS.get("get_file", set())

        for field in proto_fields:
            assert field in our_params, (
                f"Proto field '{field}' in GetFileRequest not exposed in get_file. "
                f"Our params: {our_params}"
            )


class TestNewProtoFields:
    """Informational: report any new proto fields we haven't adopted."""

    def test_report_unadopted_target_fields(self):
        proto = _fetch_proto("target.proto")
        target_fields = _parse_selector_fields(proto, "Target")
        known_fields = {
            "id",
            "label",
            "status",
            "timing",
            "rule_type",
            "tag",
            "language",
        }
        new_fields = target_fields - known_fields
        if new_fields:
            pytest.skip(
                f"New Target proto fields detected (not a failure): {new_fields}"
            )

    def test_report_unadopted_action_fields(self):
        proto = _fetch_proto("action.proto")
        action_fields = _parse_selector_fields(proto, "Action")
        known_fields = {"id", "file", "target_label", "shard", "run", "attempt"}
        new_fields = action_fields - known_fields
        if new_fields:
            pytest.skip(
                f"New Action proto fields detected (not a failure): {new_fields}"
            )
