# Homelab - Secure Kubernetes Infrastructure

A security-first Kubernetes homelab running on Talos Linux with GitOps deployment via ArgoCD.

See [CLAUDE.md](.claude/CLAUDE.md) for detailed architecture documentation.

[![Bazel CI](https://github.com/jomcgi/homelab/actions/workflows/bazel-ci.yaml/badge.svg)](https://github.com/jomcgi/homelab/actions/workflows/bazel-ci.yaml)

## Quick Start

This monorepo uses [Bazel](https://bazel.build/) for build automation and dependency management.

### Setup

```bash
# Install bazelisk (Bazel launcher)
curl -LO "https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64"
chmod +x bazelisk-linux-amd64
sudo mv bazelisk-linux-amd64 /usr/local/bin/bazel

# Build all targets
bazel build //...

# Run tests
bazel test //...
```

### Development Tasks

```bash
# Format code
bazel run //:format

# Lint code
aspect lint //...

# Run specific tests
bazel test //services/n8n_obsidian_api:test
bazel test //websites/hikes.jomcgi.dev:test
```

See [README.bazel.md](README.bazel.md) for detailed Bazel workflows.

## Monorepo Structure

```
├── services/          # Backend services (Python/Go)
│   ├── n8n_obsidian_api/
│   └── hikes/
├── operators/         # Custom Kubernetes operators
│   └── cloudflare/
├── charts/            # Helm charts
│   ├── n8n/
│   ├── cloudflare-tunnel/
│   └── n8n-obsidian-api/
├── clusters/          # Cluster entry points for ArgoCD
│   └── homelab/
├── overlays/          # Environment-specific configs
│   ├── cluster-critical/
│   ├── prod/
│   └── dev/
├── pkg/               # Shared Go libraries
│   └── n8n/
└── websites/          # Static websites
    └── hikes.jomcgi.dev/
```

## Configuration Files

- **`MODULE.bazel`** - Bazel module dependencies
- **`pyproject.toml`** - Shared Python configuration (ruff, pyright, pytest)
- **`.github/workflows/`** - CI/CD pipelines using Bazel

## CI/CD

All Python code is automatically checked on every PR:
- Linting with `ruff`
- Type checking with `pyright`
- Tests with `pytest`

See `.github/workflows/` for workflow definitions.

## Philosophy

This codebase prioritizes:
- **Simplicity over cleverness**
- **Security by default**
- **Observable, testable systems**
- **Deep modules with clean interfaces**

See [CLAUDE.md](.claude/CLAUDE.md) for detailed design principles.

## License

Part of the homelab project.
