# Tests for no-hardcoded-k8s-service-url rule.
# Hardcoded .svc.cluster.local URLs silently break when Helm release names change.
# Configure service URLs via environment variables injected from Helm values.yaml.
import os


def bad_default_parameter(
    # ruleid: no-hardcoded-k8s-service-url
    base_url: str = "http://chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123",
):
    return base_url


def bad_os_environ_get():
    # ruleid: no-hardcoded-k8s-service-url
    url = os.environ.get(
        "CLICKHOUSE_URL",
        "http://chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123",
    )
    return url


def bad_os_environ_get_inline():
    # ruleid: no-hardcoded-k8s-service-url
    url = os.environ.get(
        "OTEL_ENDPOINT",
        "http://signoz-otel-agent.signoz.svc.cluster.local:4318/v1/traces",
    )
    return url


def bad_hardcoded_assignment():
    # ruleid: no-hardcoded-k8s-service-url
    url = "http://my-service.default.svc.cluster.local:8080"
    return url


def ok_empty_string_default(
    # ok: no-hardcoded-k8s-service-url — empty string, URL injected via env
    base_url: str = "",
):
    return base_url


def ok_os_environ_get_no_fallback():
    # ok: no-hardcoded-k8s-service-url — no hardcoded fallback
    url = os.environ.get("CLICKHOUSE_URL", "")
    return url


def ok_external_url():
    # ok: no-hardcoded-k8s-service-url — not a cluster-local URL
    url = "http://example.com/api"
    return url


def ok_localhost():
    # ok: no-hardcoded-k8s-service-url — localhost is fine
    url = "http://localhost:8080"
    return url
