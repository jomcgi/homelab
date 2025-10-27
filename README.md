# Homelab - Secure Kubernetes Infrastructure

A security-first Kubernetes homelab running on Talos Linux with GitOps deployment via ArgoCD.

See [CLAUDE.md](.claude/CLAUDE.md) for detailed architecture documentation.

## Quick Start

This monorepo uses [`mise`](https://mise.jdx.dev/) for tool management and task automation.

### Setup

```bash
# Install mise (if not already installed)
curl https://mise.run | sh

# Install tools and dependencies
mise install
mise run install

# Activate mise in your shell (optional, for auto-activation)
echo 'eval "$(mise activate zsh)"' >> ~/.zshrc  # or bash/fish
```

### Development Tasks

```bash
mise run lint       # Lint all Python code (with auto-fix)
mise run format     # Format all Python code
mise run typecheck  # Type check all Python code
mise run check      # Run lint + typecheck
mise run test       # Run all tests
```

### Tool Versions

Tools are automatically installed at the versions specified in `mise.toml`:
- **Python 3.11** - For services
- **Node 20** - For websites
- **uv** - Fast Python package management

Run `mise list` to see installed tools.

## Monorepo Structure

```
├── services/          # Backend services (Python/Go)
│   └── n8n-obsidian-api/
├── operators/         # Custom Kubernetes operators
│   └── cloudflare/
├── charts/            # Helm charts
│   ├── n8n/
│   └── cloudflare-tunnel/
├── clusters/          # Cluster entry points for ArgoCD
│   └── homelab/
├── overlays/          # Environment-specific configs
│   ├── cluster-critical/
│   ├── prod/
│   └── dev/
└── websites/          # Static websites
    └── hikes.jomcgi.dev/
```

## Configuration Files

- **`mise.toml`** - Tool versions and monorepo tasks
- **`pyproject.toml`** - Shared Python configuration (ruff, pyright, pytest)
- **`.github/workflows/`** - CI/CD pipelines using mise

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
