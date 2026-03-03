package gazelle

import (
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// semgrepConfig holds configuration for the semgrep Gazelle extension.
type semgrepConfig struct {
	// enabled controls whether to generate rules in this directory
	enabled bool
	// excludeRules is a list of semgrep rule IDs to exclude
	excludeRules []string
}

const semgrepConfigKey = "semgrep_config"

// getSemgrepConfig retrieves the semgrep configuration from a Bazel config.
func getSemgrepConfig(c *config.Config) *semgrepConfig {
	if cfg, ok := c.Exts[semgrepConfigKey].(*semgrepConfig); ok {
		return cfg
	}
	// Default configuration
	return &semgrepConfig{
		enabled: true,
	}
}

// configure reads semgrep-specific directives from BUILD files.
func configure(c *config.Config, rel string, f *rule.File) {
	// Start with the parent directory's configuration
	parent := getSemgrepConfig(c)

	// Clone the parent configuration
	cfg := &semgrepConfig{
		enabled:      parent.enabled,
		excludeRules: append([]string{}, parent.excludeRules...),
	}

	// Process directives if a BUILD file exists
	if f != nil {
		for _, d := range f.Directives {
			switch d.Key {
			case "semgrep":
				// # gazelle:semgrep enabled
				// # gazelle:semgrep disabled
				cfg.enabled = d.Value != "disabled"
			case "semgrep_exclude_rules":
				// # gazelle:semgrep_exclude_rules rule1,rule2
				if d.Value != "" {
					cfg.excludeRules = strings.Split(d.Value, ",")
					for i, r := range cfg.excludeRules {
						cfg.excludeRules[i] = strings.TrimSpace(r)
					}
				}
			}
		}
	}

	// Store the configuration
	c.Exts[semgrepConfigKey] = cfg
}
