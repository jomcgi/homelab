package gazelle

import (
	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// wranglerConfig holds configuration for the wrangler Gazelle extension.
type wranglerConfig struct {
	// enabled controls whether to generate rules in this directory
	enabled bool
	// dist is the default dist label for wrangler_pages targets
	dist string
}

const wranglerConfigKey = "wrangler_config"

// getWranglerConfig retrieves the wrangler configuration from a Bazel config.
func getWranglerConfig(c *config.Config) *wranglerConfig {
	if cfg, ok := c.Exts[wranglerConfigKey].(*wranglerConfig); ok {
		return cfg
	}
	// Default configuration
	return &wranglerConfig{
		enabled: true,
		dist:    ":build_dist",
	}
}

// configure reads wrangler-specific directives from BUILD files.
func configure(c *config.Config, rel string, f *rule.File) {
	// Start with the parent directory's configuration
	parent := getWranglerConfig(c)

	// Clone the parent configuration
	cfg := &wranglerConfig{
		enabled: parent.enabled,
		dist:    parent.dist,
	}

	// Process directives if a BUILD file exists
	if f != nil {
		for _, d := range f.Directives {
			switch d.Key {
			case "wrangler":
				// # gazelle:wrangler enabled
				// # gazelle:wrangler disabled
				if len(d.Value) > 0 {
					cfg.enabled = d.Value == "enabled"
				}

			case "wrangler_enabled":
				// # gazelle:wrangler_enabled
				cfg.enabled = true

			case "wrangler_dist":
				// # gazelle:wrangler_dist :public
				if len(d.Value) > 0 {
					cfg.dist = d.Value
				}
			}
		}
	}

	// Store the configuration
	c.Exts[wranglerConfigKey] = cfg
}
