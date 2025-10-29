package argocd

import (
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// argoCDConfig holds configuration for the ArgoCD Gazelle extension.
type argoCDConfig struct {
	// enabled controls whether to generate rules in this directory
	enabled bool
	// baseBranch is the default base branch for diffs
	baseBranch string
	// clusters is a list of cluster names to generate diff targets for
	clusters []string
	// clusterSnapshotImages maps cluster names to snapshot image URLs
	clusterSnapshotImages map[string]string
}

const argoCDConfigKey = "argocd_config"

// getArgoCDConfig retrieves the ArgoCD configuration from a Bazel config.
func getArgoCDConfig(c *config.Config) *argoCDConfig {
	if cfg, ok := c.Exts[argoCDConfigKey].(*argoCDConfig); ok {
		return cfg
	}
	// Default configuration
	return &argoCDConfig{
		enabled:               true, // Enabled by default
		baseBranch:            "origin/main",
		clusters:              []string{},
		clusterSnapshotImages: make(map[string]string),
	}
}

// configure reads ArgoCD-specific directives from BUILD files.
func configure(c *config.Config, rel string, f *rule.File) {
	// Start with the parent directory's configuration
	parent := getArgoCDConfig(c)

	// Clone the parent configuration
	cfg := &argoCDConfig{
		enabled:               parent.enabled,
		baseBranch:            parent.baseBranch,
		clusters:              append([]string{}, parent.clusters...),
		clusterSnapshotImages: make(map[string]string),
	}

	// Copy cluster snapshot images
	for k, v := range parent.clusterSnapshotImages {
		cfg.clusterSnapshotImages[k] = v
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

			case "argocd_base_branch":
				// # gazelle:argocd_base_branch origin/develop
				if len(d.Value) > 0 {
					cfg.baseBranch = d.Value
				}

			case "argocd_clusters":
				// # gazelle:argocd_clusters cluster1,cluster2,cluster3
				if len(d.Value) > 0 {
					cfg.clusters = strings.Split(d.Value, ",")
					for i := range cfg.clusters {
						cfg.clusters[i] = strings.TrimSpace(cfg.clusters[i])
					}
				}

			case "argocd_cluster_snapshot":
				// # gazelle:argocd_cluster_snapshot cluster1=ghcr.io/jomcgi/argocd-preview:cluster1
				if len(d.Value) > 0 && strings.Contains(d.Value, "=") {
					parts := strings.SplitN(d.Value, "=", 2)
					cluster := strings.TrimSpace(parts[0])
					image := strings.TrimSpace(parts[1])
					cfg.clusterSnapshotImages[cluster] = image
				}
			}
		}
	}

	// Store the configuration
	c.Exts[argoCDConfigKey] = cfg
}
