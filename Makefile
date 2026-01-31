# Homelab Makefile
# Run 'make help' to see available targets
#
# All tests run via Bazel for caching and reproducibility.

.PHONY: help test test-go test-charts test-charts-local

# Default target
help:
	@echo "Available targets:"
	@echo "  test              - Run all tests via Bazel (Go + Helm charts)"
	@echo "  test-go           - Run Go tests via Bazel"
	@echo "  test-charts       - Run Helm chart lint tests via Bazel"
	@echo "  test-charts-local - Run helm lint locally (all charts)"

# Run all tests via Bazel
test:
	@echo "==> Running all tests via Bazel..."
	bazelisk test //tools/argocd:argocd_test //charts/api-gateway:lint_test //charts/cloudflare-operator-test:lint_test //charts/stargazer:lint_test

# Run Go tests via Bazel
test-go:
	@echo "==> Running Go tests via Bazel..."
	bazelisk test //tools/argocd:argocd_test

# Run Helm chart lint tests via Bazel
test-charts:
	@echo "==> Running chart lint tests via Bazel..."
	bazelisk test --test_tag_filters=chart //charts/...

# Run helm lint locally on all charts (without Bazel)
test-charts-local:
	@echo "==> Running helm lint locally on all charts..."
	@./scripts/test-charts.sh
