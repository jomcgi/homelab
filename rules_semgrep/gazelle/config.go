package gazelle

import (
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// langRules maps language keys to their semgrep rule config labels.
var langRules = map[string]string{
	"py": "//semgrep_rules:python_rules",
	"go": "//semgrep_rules:golang_rules",
}

// langExtensions maps language keys to their file extensions.
var langExtensions = map[string]string{
	"py": ".py",
	"go": ".go",
}

// defaultTargetKinds is the default set of rule kinds that trigger
// semgrep_target_test generation. The value is the attr to follow
// ("" means the target itself).
var defaultTargetKinds = map[string]string{
	"py_venv_binary": "",
}

// defaultLanguages is the default set of languages to scan.
var defaultLanguages = []string{"py"}

// semgrepConfig holds configuration for the semgrep Gazelle extension.
type semgrepConfig struct {
	// enabled controls whether to generate rules in this directory
	enabled bool
	// excludeRules is a list of semgrep rule IDs to exclude
	excludeRules []string
	// targetKinds maps rule kind → attr name. "" means the target itself,
	// a non-empty string means follow that attr to find the real target.
	targetKinds map[string]string
	// languages lists the language keys to scan (e.g. "py", "go").
	languages []string
}

const semgrepConfigKey = "semgrep_config"

// getSemgrepConfig retrieves the semgrep configuration from a Bazel config.
func getSemgrepConfig(c *config.Config) *semgrepConfig {
	if cfg, ok := c.Exts[semgrepConfigKey].(*semgrepConfig); ok {
		return cfg
	}
	// Default configuration
	return &semgrepConfig{
		enabled:     true,
		targetKinds: copyTargetKinds(defaultTargetKinds),
		languages:   append([]string{}, defaultLanguages...),
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
		targetKinds:  copyTargetKinds(parent.targetKinds),
		languages:    append([]string{}, parent.languages...),
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
			case "semgrep_target_kinds":
				// # gazelle:semgrep_target_kinds py_venv_binary,py3_image=binary
				if d.Value != "" {
					cfg.targetKinds = parseTargetKinds(d.Value)
				}
			case "semgrep_languages":
				// # gazelle:semgrep_languages py,go
				if d.Value != "" {
					cfg.languages = parseLanguages(d.Value)
				}
			}
		}
	}

	// Store the configuration
	c.Exts[semgrepConfigKey] = cfg
}

// parseTargetKinds parses a comma-separated list of kind or kind=attr pairs.
// "py_venv_binary" → {"py_venv_binary": ""}
// "py3_image=binary" → {"py3_image": "binary"}
func parseTargetKinds(value string) map[string]string {
	kinds := make(map[string]string)
	for _, entry := range strings.Split(value, ",") {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}
		if idx := strings.Index(entry, "="); idx >= 0 {
			kind := strings.TrimSpace(entry[:idx])
			attr := strings.TrimSpace(entry[idx+1:])
			if kind != "" {
				kinds[kind] = attr
			}
		} else {
			kinds[entry] = ""
		}
	}
	return kinds
}

// parseLanguages parses a comma-separated list of language keys.
func parseLanguages(value string) []string {
	var langs []string
	for _, lang := range strings.Split(value, ",") {
		lang = strings.TrimSpace(lang)
		if lang != "" {
			langs = append(langs, lang)
		}
	}
	return langs
}

// copyTargetKinds creates a shallow copy of a targetKinds map.
func copyTargetKinds(src map[string]string) map[string]string {
	if src == nil {
		return nil
	}
	dst := make(map[string]string, len(src))
	for k, v := range src {
		dst[k] = v
	}
	return dst
}
