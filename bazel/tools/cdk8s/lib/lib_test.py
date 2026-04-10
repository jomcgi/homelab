"""Tests for bazel/tools/cdk8s/lib/__init__.py.

Covers Labels and ResourceRequirements dataclasses — pure Python,
no cdk8s or Kubernetes imports required.
"""

from __future__ import annotations

import os
import sys

# Ensure the cdk8s root is on sys.path so `lib` is importable as `lib`
# (mirrors the sys.path.insert that main.py performs at startup).
_HERE = os.path.dirname(os.path.abspath(__file__))
_CDK8S_ROOT = os.path.dirname(_HERE)
if _CDK8S_ROOT not in sys.path:
    sys.path.insert(0, _CDK8S_ROOT)

import pytest

from lib import Labels, ResourceRequirements


# ---------------------------------------------------------------------------
# ResourceRequirements — defaults
# ---------------------------------------------------------------------------


class TestResourceRequirementsDefaults:
    def test_cpu_limit_default(self):
        r = ResourceRequirements()
        assert r.cpu_limit == "100m"

    def test_memory_limit_default(self):
        r = ResourceRequirements()
        assert r.memory_limit == "64Mi"

    def test_cpu_request_default(self):
        r = ResourceRequirements()
        assert r.cpu_request == "10m"

    def test_memory_request_default(self):
        r = ResourceRequirements()
        assert r.memory_request == "32Mi"


# ---------------------------------------------------------------------------
# ResourceRequirements — custom values
# ---------------------------------------------------------------------------


class TestResourceRequirementsCustom:
    def test_all_custom_values_stored(self):
        r = ResourceRequirements(
            cpu_limit="500m",
            memory_limit="256Mi",
            cpu_request="50m",
            memory_request="128Mi",
        )
        assert r.cpu_limit == "500m"
        assert r.memory_limit == "256Mi"
        assert r.cpu_request == "50m"
        assert r.memory_request == "128Mi"

    def test_partial_override_leaves_other_defaults_unchanged(self):
        r = ResourceRequirements(cpu_limit="200m")
        assert r.cpu_limit == "200m"
        assert r.memory_limit == "64Mi"
        assert r.cpu_request == "10m"
        assert r.memory_request == "32Mi"

    def test_zero_cpu_request_allowed(self):
        r = ResourceRequirements(cpu_request="0m")
        assert r.cpu_request == "0m"

    def test_large_memory_limit_stored(self):
        r = ResourceRequirements(memory_limit="16Gi")
        assert r.memory_limit == "16Gi"


# ---------------------------------------------------------------------------
# Labels.common()
# ---------------------------------------------------------------------------


class TestLabelsCommon:
    def test_name_present(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert lbl.common()["app.kubernetes.io/name"] == "myapp"

    def test_instance_present(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert lbl.common()["app.kubernetes.io/instance"] == "rel1"

    def test_version_present(self):
        lbl = Labels(name="myapp", instance="rel1", version="2.3")
        assert lbl.common()["app.kubernetes.io/version"] == "2.3"

    def test_managed_by_default_is_cdk8s(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert lbl.common()["app.kubernetes.io/managed-by"] == "cdk8s"

    def test_managed_by_custom_value(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", managed_by="Helm")
        assert lbl.common()["app.kubernetes.io/managed-by"] == "Helm"

    def test_chart_label_present_when_set(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", chart="myapp-1.0")
        assert lbl.common()["helm.sh/chart"] == "myapp-1.0"

    def test_chart_label_absent_when_not_set(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert "helm.sh/chart" not in lbl.common()

    def test_chart_label_absent_when_none(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", chart=None)
        assert "helm.sh/chart" not in lbl.common()

    def test_component_label_present_when_set(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", component="backend")
        assert lbl.common()["app.kubernetes.io/component"] == "backend"

    def test_component_label_absent_when_not_set(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert "app.kubernetes.io/component" not in lbl.common()

    def test_component_label_absent_when_none(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", component=None)
        assert "app.kubernetes.io/component" not in lbl.common()

    def test_returns_dict(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert isinstance(lbl.common(), dict)

    def test_minimum_four_keys_without_optionals(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        result = lbl.common()
        assert len(result) == 4

    def test_six_keys_with_both_optionals(self):
        lbl = Labels(
            name="myapp",
            instance="rel1",
            version="1.0",
            component="web",
            chart="myapp-1.0",
        )
        result = lbl.common()
        assert len(result) == 6

    def test_common_returns_new_dict_each_call(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        d1 = lbl.common()
        d2 = lbl.common()
        assert d1 == d2
        assert d1 is not d2  # Different dict objects


# ---------------------------------------------------------------------------
# Labels.selector()
# ---------------------------------------------------------------------------


class TestLabelsSelector:
    def test_contains_name(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert lbl.selector()["app.kubernetes.io/name"] == "myapp"

    def test_contains_instance(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert lbl.selector()["app.kubernetes.io/instance"] == "rel1"

    def test_does_not_contain_version(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert "app.kubernetes.io/version" not in lbl.selector()

    def test_does_not_contain_managed_by(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert "app.kubernetes.io/managed-by" not in lbl.selector()

    def test_does_not_contain_chart(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", chart="mychart-1.0")
        assert "helm.sh/chart" not in lbl.selector()

    def test_component_present_when_set(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", component="frontend")
        assert lbl.selector()["app.kubernetes.io/component"] == "frontend"

    def test_component_absent_when_not_set(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert "app.kubernetes.io/component" not in lbl.selector()

    def test_selector_is_subset_of_common(self):
        """Every selector key+value must appear in common()."""
        lbl = Labels(
            name="myapp",
            instance="rel1",
            version="1.0",
            component="web",
            chart="c-1",
        )
        selector = lbl.selector()
        common = lbl.common()
        for key, value in selector.items():
            assert common.get(key) == value, (
                f"key {key!r} = {value!r} in selector not found in common()"
            )

    def test_returns_dict(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert isinstance(lbl.selector(), dict)

    def test_exactly_two_keys_without_component(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        assert len(lbl.selector()) == 2

    def test_exactly_three_keys_with_component(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0", component="web")
        assert len(lbl.selector()) == 3

    def test_selector_returns_new_dict_each_call(self):
        lbl = Labels(name="myapp", instance="rel1", version="1.0")
        s1 = lbl.selector()
        s2 = lbl.selector()
        assert s1 == s2
        assert s1 is not s2


# ---------------------------------------------------------------------------
# Labels — edge cases
# ---------------------------------------------------------------------------


class TestLabelsEdgeCases:
    def test_version_defaults_to_1_0(self):
        lbl = Labels(name="app", instance="inst")
        assert lbl.version == "1.0"

    def test_managed_by_defaults_to_cdk8s(self):
        lbl = Labels(name="app", instance="inst")
        assert lbl.managed_by == "cdk8s"

    def test_empty_string_name(self):
        lbl = Labels(name="", instance="inst", version="1.0")
        assert lbl.common()["app.kubernetes.io/name"] == ""

    def test_hyphenated_name_preserved(self):
        lbl = Labels(name="my-app-v2", instance="rel1", version="1.0")
        assert lbl.common()["app.kubernetes.io/name"] == "my-app-v2"
        assert lbl.selector()["app.kubernetes.io/name"] == "my-app-v2"
