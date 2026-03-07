load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "agent-sandbox",
    chart = "charts/agent-sandbox",
    chart_files = "//charts/agent-sandbox:chart",
    namespace = "agent-sandbox-system",
    release_name = "agent-sandbox",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/agent-sandbox:values.yaml",
        "values.yaml",
    ],
)
