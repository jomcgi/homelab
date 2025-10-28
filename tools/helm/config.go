package helm

import (
	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// argoCDConfig holds configuration for the ArgoCD Gazelle extension.
type argoCDConfig struct {
	// enabled controls whether to generate rules in this directory
	enabled bool
	// generateDiff controls whether to generate helm_diff_script rules
	generateDiff bool
	// kubectlContext is the kubectl context to use for diff operations
	kubectlContext string
}

const argoCDConfigKey = "argocd_config"

// getArgoCDConfig retrieves the ArgoCD configuration from a Bazel config.
func getArgoCDConfig(c *config.Config) *argoCDConfig {
	if cfg, ok := c.Exts[argoCDConfigKey].(*argoCDConfig); ok {
		return cfg
	}
	// Default configuration
	return &argoCDConfig{
		enabled:        true, // Enabled by default
		generateDiff:   false,
		kubectlContext: "current",
	}
}

// configure reads ArgoCD-specific directives from BUILD files.
func configure(c *config.Config, rel string, f *rule.File) {
	// Start with the parent directory's configuration
	parent := getArgoCDConfig(c)

	// Clone the parent configuration
	cfg := &argoCDConfig{
		enabled:        parent.enabled,
		generateDiff:   parent.generateDiff,
		kubectlContext: parent.kubectlContext,
	}

	// Process directives if a BUILD file exists
	if f != nil {
		for _, d := range f.Directives {
			switch d.Key {
			case "argocd":
				// # gazelle:argocd enabled
				// # gazelle:argocd disabled
				if len(d.Value) > 0 {
					cfg.enabled = d.Value == "enabled"
				}

			case "argocd_enabled":
				// # gazelle:argocd_enabled
				cfg.enabled = true

			case "argocd_generate_diff":
				// # gazelle:argocd_generate_diff true
				// # gazelle:argocd_generate_diff false
				cfg.generateDiff = d.Value == "true"

			case "kubectl_context":
				// # gazelle:kubectl_context homelab
				if len(d.Value) > 0 {
					cfg.kubectlContext = d.Value
				}
			}
		}
	}

	// Store the configuration
	c.Exts[argoCDConfigKey] = cfg
}
