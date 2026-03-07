load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "agent-orchestrator",
    chart = "charts/agent-orchestrator",
    chart_files = "//charts/agent-orchestrator:chart",
    namespace = "agent-orchestrator",
    release_name = "agent-orchestrator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/agent-orchestrator:values.yaml",
        "values.yaml",
    ],
)
