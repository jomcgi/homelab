load("//bazel/helm:defs.bzl", "argocd_app", "helm_annotation_test", "helm_chart")

helm_chart(
    name = "chart",
    images = {
        "image": "//projects/agent_platform/cluster_agents:image.info",
    },
    publish = True,
    visibility = ["//overlays:__subpackages__"],
)

argocd_app(
    name = "cluster-agents",
    chart = "projects/agent_platform/cluster_agents/deploy",
    chart_files = ":chart",
    namespace = "cluster-agents",
    release_name = "cluster-agents",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "values.yaml",
    ],
)

# Regression test: cluster-agents namespace has Linkerd injection enabled via Kyverno.
# SigNoz httpcheck runs from the unmeshed signoz namespace. Without this annotation,
# Linkerd drops inbound port 8080 connections and fires the 'cluster-agents Unreachable'
# alert (rule 019cda4d). See values.yaml for the annotation and docs in application.yaml.
helm_annotation_test(
    name = "linkerd_annotation_test",
    annotations = ["config.linkerd.io/skip-inbound-ports:8080"],
    chart = "projects/agent_platform/cluster_agents/deploy",
    chart_files = ":chart",
    namespace = "cluster-agents",
    release_name = "cluster-agents",
    tags = ["helm"],
)
