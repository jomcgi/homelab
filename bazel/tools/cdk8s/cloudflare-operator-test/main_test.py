"""Tests for bazel/tools/cdk8s/cloudflare-operator-test/main.py.

Mocks cdk8s/constructs/imports.k8s so these tests run in the Bazel
hermetic sandbox without npm packages or a running cluster.

Strategy: all k8s constructors (KubeService, KubeDeployment, ObjectMeta, etc.)
are MagicMocks. We assert on the *arguments passed to those constructors* rather
than on properties of their return values (which are also mocks). This is the
correct way to verify cdk8s manifest-generation logic without a live environment.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import ANY, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Set up mock modules BEFORE importing main.py.
# We provide real Python base classes for Construct and Chart so that
# Python's class machinery works for subclasses defined in main.py.
# ---------------------------------------------------------------------------


class _MockConstruct:
    """Minimal stand-in for constructs.Construct."""

    def __init__(self, scope, id, **kwargs):
        self._scope = scope
        self._id = id


class _MockChart(_MockConstruct):
    """Minimal stand-in for cdk8s.Chart."""

    pass


class _MockApp:
    """Minimal stand-in for cdk8s.App — synth() is a no-op."""

    def synth(self):
        pass


# k8s is a MagicMock so every attribute access (KubeService, KubeDeployment,
# ObjectMeta, ...) returns a callable mock that records its call arguments.
_mock_k8s = MagicMock(name="imports.k8s")

_mock_cdk8s_mod = types.SimpleNamespace(App=_MockApp, Chart=_MockChart)
_mock_constructs_mod = types.SimpleNamespace(Construct=_MockConstruct)
_mock_imports_mod = types.SimpleNamespace(k8s=_mock_k8s)

sys.modules.setdefault("cdk8s", _mock_cdk8s_mod)
sys.modules.setdefault("constructs", _mock_constructs_mod)
sys.modules.setdefault("imports", _mock_imports_mod)
sys.modules.setdefault("imports.k8s", _mock_k8s)

# Ensure lib is importable as `lib` (mirrors the sys.path manipulation in main.py)
_HERE = os.path.dirname(os.path.abspath(__file__))
_CDK8S_ROOT = os.path.dirname(_HERE)
if _CDK8S_ROOT not in sys.path:
    sys.path.insert(0, _CDK8S_ROOT)

# Load main.py via importlib so we control __file__ and the module-level
# app.synth() runs against our mock App (safe no-op).
_MAIN_PY = os.path.join(_HERE, "main.py")
_spec = importlib.util.spec_from_file_location("cf_main", _MAIN_PY)
_cf_main = importlib.util.module_from_spec(_spec)
# Pre-populate sys.modules to avoid re-loading on subsequent imports
sys.modules.setdefault("cf_main", _cf_main)
_spec.loader.exec_module(_cf_main)

ClusterIPService = _cf_main.ClusterIPService
SecureDeployment = _cf_main.SecureDeployment
CloudflareOperatorTestChart = _cf_main.CloudflareOperatorTestChart

from lib import Labels, ResourceRequirements  # noqa: E402  (after path setup)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_k8s_mocks():
    """Reset the k8s mock call counters before every test."""
    _mock_k8s.reset_mock()
    yield


def _scope():
    """Return a fresh mock scope (root Construct)."""
    return _MockConstruct(None, "root")


def _labels(**kwargs):
    defaults = dict(name="app", instance="rel", version="1.0")
    defaults.update(kwargs)
    return Labels(**defaults)


# ---------------------------------------------------------------------------
# ClusterIPService — annotation-building logic
# ---------------------------------------------------------------------------


class TestClusterIPServiceAnnotations:
    """Test the annotation dict constructed by ClusterIPService."""

    def _service_annotations(self, **kwargs):
        """Create a ClusterIPService and return the annotations kwarg passed to ObjectMeta."""
        ClusterIPService(_scope(), "svc", name="my-svc", labels=_labels(), **kwargs)
        # ObjectMeta is called once for the service metadata
        return _mock_k8s.ObjectMeta.call_args.kwargs.get("annotations")

    def test_no_annotations_when_nothing_set(self):
        annotations = self._service_annotations()
        assert annotations is None

    def test_hostname_annotation_set(self):
        annotations = self._service_annotations(cloudflare_hostname="app.example.com")
        assert annotations is not None
        assert annotations["cloudflare.ingress.hostname"] == "app.example.com"

    def test_empty_hostname_omits_annotation(self):
        """Empty string is falsy — annotation must not be added."""
        annotations = self._service_annotations(cloudflare_hostname="")
        assert annotations is None

    def test_zero_trust_enabled_true_produces_string_true(self):
        annotations = self._service_annotations(cloudflare_zero_trust_enabled=True)
        assert annotations["cloudflare.zero-trust.enabled"] == "true"

    def test_zero_trust_enabled_false_produces_string_false(self):
        annotations = self._service_annotations(cloudflare_zero_trust_enabled=False)
        assert annotations["cloudflare.zero-trust.enabled"] == "false"

    def test_zero_trust_enabled_none_omits_annotation(self):
        """None means "not set" — the annotation key must not appear."""
        annotations = self._service_annotations(cloudflare_zero_trust_enabled=None)
        assert annotations is None

    def test_zero_trust_policy_annotation_set(self):
        annotations = self._service_annotations(cloudflare_zero_trust_policy="joe-only")
        assert annotations["cloudflare.zero-trust.policy"] == "joe-only"

    def test_all_three_annotations_combined(self):
        annotations = self._service_annotations(
            cloudflare_hostname="app.example.com",
            cloudflare_zero_trust_enabled=True,
            cloudflare_zero_trust_policy="admins",
        )
        assert annotations["cloudflare.ingress.hostname"] == "app.example.com"
        assert annotations["cloudflare.zero-trust.enabled"] == "true"
        assert annotations["cloudflare.zero-trust.policy"] == "admins"

    def test_hostname_only_no_zero_trust_keys(self):
        annotations = self._service_annotations(cloudflare_hostname="app.example.com")
        assert "cloudflare.zero-trust.enabled" not in annotations
        assert "cloudflare.zero-trust.policy" not in annotations

    def test_service_name_passed_to_object_meta(self):
        ClusterIPService(_scope(), "svc", name="special-svc", labels=_labels())
        kwargs = _mock_k8s.ObjectMeta.call_args.kwargs
        assert kwargs["name"] == "special-svc"

    def test_kube_service_created(self):
        ClusterIPService(_scope(), "svc", name="my-svc", labels=_labels())
        _mock_k8s.KubeService.assert_called_once()

    def test_default_port_80(self):
        ClusterIPService(_scope(), "svc", name="my-svc", labels=_labels())
        port_call = _mock_k8s.ServicePort.call_args
        assert port_call.kwargs["port"] == 80

    def test_custom_port(self):
        ClusterIPService(_scope(), "svc", name="my-svc", labels=_labels(), port=8080)
        port_call = _mock_k8s.ServicePort.call_args
        assert port_call.kwargs["port"] == 8080

    def test_service_type_is_cluster_ip(self):
        ClusterIPService(_scope(), "svc", name="my-svc", labels=_labels())
        spec_call = _mock_k8s.ServiceSpec.call_args
        assert spec_call.kwargs["type"] == "ClusterIP"

    def test_default_target_port_is_http(self):
        ClusterIPService(_scope(), "svc", name="my-svc", labels=_labels())
        port_call = _mock_k8s.ServicePort.call_args
        # target_port is constructed via IntOrString.from_string("http")
        _mock_k8s.IntOrString.from_string.assert_called_with("http")


# ---------------------------------------------------------------------------
# SecureDeployment — security-context and resource values
# ---------------------------------------------------------------------------


class TestSecureDeployment:
    def _create(self, **kwargs):
        defaults = dict(
            name="my-dep",
            image="hashicorp/http-echo:1.0",
            port=5678,
            labels=_labels(),
        )
        defaults.update(kwargs)
        SecureDeployment(_scope(), "dep", **defaults)

    def test_kube_deployment_created(self):
        self._create()
        _mock_k8s.KubeDeployment.assert_called_once()

    def test_deployment_name_in_object_meta(self):
        self._create(name="named-dep")
        # The first ObjectMeta call is for the deployment metadata
        first_meta_call = _mock_k8s.ObjectMeta.call_args_list[0]
        assert first_meta_call.kwargs["name"] == "named-dep"

    def test_replicas_default_is_1(self):
        self._create()
        spec_call = _mock_k8s.DeploymentSpec.call_args
        assert spec_call.kwargs["replicas"] == 1

    def test_replicas_custom(self):
        self._create(replicas=3)
        spec_call = _mock_k8s.DeploymentSpec.call_args
        assert spec_call.kwargs["replicas"] == 3

    def test_pod_security_context_run_as_non_root(self):
        self._create()
        sec_ctx_call = _mock_k8s.PodSecurityContext.call_args
        assert sec_ctx_call.kwargs["run_as_non_root"] is True

    def test_pod_security_context_run_as_user_65534(self):
        self._create()
        sec_ctx_call = _mock_k8s.PodSecurityContext.call_args
        assert sec_ctx_call.kwargs["run_as_user"] == 65534

    def test_pod_security_context_fs_group_65534(self):
        self._create()
        sec_ctx_call = _mock_k8s.PodSecurityContext.call_args
        assert sec_ctx_call.kwargs["fs_group"] == 65534

    def test_container_security_no_privilege_escalation(self):
        self._create()
        container_sec_call = _mock_k8s.SecurityContext.call_args
        assert container_sec_call.kwargs["allow_privilege_escalation"] is False

    def test_container_security_read_only_root_filesystem(self):
        self._create()
        container_sec_call = _mock_k8s.SecurityContext.call_args
        assert container_sec_call.kwargs["read_only_root_filesystem"] is True

    def test_container_security_run_as_non_root(self):
        self._create()
        container_sec_call = _mock_k8s.SecurityContext.call_args
        assert container_sec_call.kwargs["run_as_non_root"] is True

    def test_container_image_passed(self):
        self._create(image="myrepo/myimage:v2")
        container_call = _mock_k8s.Container.call_args
        assert container_call.kwargs["image"] == "myrepo/myimage:v2"

    def test_container_name_is_http_echo(self):
        self._create()
        container_call = _mock_k8s.Container.call_args
        assert container_call.kwargs["name"] == "http-echo"

    def test_capabilities_drop_all(self):
        self._create()
        capabilities_call = _mock_k8s.Capabilities.call_args
        assert capabilities_call.kwargs["drop"] == ["ALL"]

    def test_image_pull_policy_if_not_present(self):
        self._create()
        container_call = _mock_k8s.Container.call_args
        assert container_call.kwargs["image_pull_policy"] == "IfNotPresent"

    def test_container_port_protocol_tcp(self):
        self._create(port=8080)
        port_call = _mock_k8s.ContainerPort.call_args
        assert port_call.kwargs["protocol"] == "TCP"

    def test_container_port_value(self):
        self._create(port=9090)
        port_call = _mock_k8s.ContainerPort.call_args
        assert port_call.kwargs["container_port"] == 9090

    def test_args_empty_when_not_provided(self):
        self._create()
        container_call = _mock_k8s.Container.call_args
        assert container_call.kwargs["args"] == []

    def test_args_passed_through(self):
        self._create(args=["-text=hello", "-listen=:5678"])
        container_call = _mock_k8s.Container.call_args
        assert container_call.kwargs["args"] == ["-text=hello", "-listen=:5678"]

    def test_default_resources_used_when_none_provided(self):
        """When resources=None, defaults from ResourceRequirements() are used."""
        self._create()
        # k8s.Quantity.from_string should be called with the default values
        call_strings = [
            c.args[0] for c in _mock_k8s.Quantity.from_string.call_args_list
        ]
        assert "100m" in call_strings  # default cpu_limit
        assert "64Mi" in call_strings  # default memory_limit


# ---------------------------------------------------------------------------
# CloudflareOperatorTestChart — enable/disable and naming
# ---------------------------------------------------------------------------


class TestCloudflareOperatorTestChart:
    def _create(self, **kwargs):
        return CloudflareOperatorTestChart(_scope(), "test-chart", **kwargs)

    def test_both_deployments_created_by_default(self):
        self._create()
        assert _mock_k8s.KubeDeployment.call_count == 2

    def test_both_services_created_by_default(self):
        self._create()
        assert _mock_k8s.KubeService.call_count == 2

    def test_noauth_disabled_creates_one_deployment(self):
        self._create(noauth_enabled=False)
        assert _mock_k8s.KubeDeployment.call_count == 1

    def test_noauth_disabled_creates_one_service(self):
        self._create(noauth_enabled=False)
        assert _mock_k8s.KubeService.call_count == 1

    def test_auth_disabled_creates_one_deployment(self):
        self._create(auth_enabled=False)
        assert _mock_k8s.KubeDeployment.call_count == 1

    def test_auth_disabled_creates_one_service(self):
        self._create(auth_enabled=False)
        assert _mock_k8s.KubeService.call_count == 1

    def test_both_disabled_creates_nothing(self):
        self._create(noauth_enabled=False, auth_enabled=False)
        assert _mock_k8s.KubeDeployment.call_count == 0
        assert _mock_k8s.KubeService.call_count == 0

    def test_image_constructed_from_repo_and_tag(self):
        self._create(
            image_repository="myrepo/myimage",
            image_tag="2.0",
            auth_enabled=False,
        )
        container_call = _mock_k8s.Container.call_args
        assert container_call.kwargs["image"] == "myrepo/myimage:2.0"

    def test_default_release_name_in_deployment_name(self):
        self._create(auth_enabled=False)
        first_meta = _mock_k8s.ObjectMeta.call_args_list[0]
        name = first_meta.kwargs["name"]
        assert name.startswith("cf-test-")

    def test_custom_release_name_in_deployment_name(self):
        self._create(release_name="myrelease", auth_enabled=False)
        first_meta = _mock_k8s.ObjectMeta.call_args_list[0]
        name = first_meta.kwargs["name"]
        assert name.startswith("myrelease-")

    def test_noauth_service_has_zero_trust_enabled_false_annotation(self):
        """The noauth service must have cloudflare.zero-trust.enabled=false."""
        self._create(auth_enabled=False)
        # With only noauth enabled, ObjectMeta is called for:
        #   1. noauth deployment metadata
        #   2. noauth pod template metadata
        #   3. noauth service metadata  ← has annotations
        # The service ObjectMeta has annotations kwarg set (not None)
        service_meta = next(
            c
            for c in _mock_k8s.ObjectMeta.call_args_list
            if c.kwargs.get("annotations") is not None
        )
        assert (
            service_meta.kwargs["annotations"]["cloudflare.zero-trust.enabled"]
            == "false"
        )

    def test_auth_service_has_zero_trust_policy(self):
        """The auth service must have cloudflare.zero-trust.policy annotation."""
        self._create(noauth_enabled=False, auth_policy="admins")
        service_meta = next(
            c
            for c in _mock_k8s.ObjectMeta.call_args_list
            if c.kwargs.get("annotations") is not None
        )
        assert (
            service_meta.kwargs["annotations"]["cloudflare.zero-trust.policy"]
            == "admins"
        )

    def test_noauth_service_hostname_annotation(self):
        """The noauth service must carry its Cloudflare hostname annotation."""
        self._create(
            auth_enabled=False,
            noauth_hostname="noauth.example.com",
        )
        service_meta = next(
            c
            for c in _mock_k8s.ObjectMeta.call_args_list
            if c.kwargs.get("annotations") is not None
        )
        assert (
            service_meta.kwargs["annotations"]["cloudflare.ingress.hostname"]
            == "noauth.example.com"
        )

    def test_auth_service_hostname_annotation(self):
        """The auth service must carry its Cloudflare hostname annotation."""
        self._create(
            noauth_enabled=False,
            auth_hostname="auth.example.com",
        )
        service_meta = next(
            c
            for c in _mock_k8s.ObjectMeta.call_args_list
            if c.kwargs.get("annotations") is not None
        )
        assert (
            service_meta.kwargs["annotations"]["cloudflare.ingress.hostname"]
            == "auth.example.com"
        )

    def test_noauth_replicas_custom(self):
        self._create(noauth_replicas=2, auth_enabled=False)
        spec_call = _mock_k8s.DeploymentSpec.call_args
        assert spec_call.kwargs["replicas"] == 2

    def test_auth_replicas_custom(self):
        self._create(noauth_enabled=False, auth_replicas=3)
        spec_call = _mock_k8s.DeploymentSpec.call_args
        assert spec_call.kwargs["replicas"] == 3
