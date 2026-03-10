package gazelle

import (
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/rule"
)

// depPrefixToEcosystem maps external dep label prefixes to lockfile ecosystems.
var depPrefixToEcosystem = map[string]string{
	"@pip//":     "pip",
	"@npm//":     "pnpm",
	"@go_deps//": "gomod",
}

// defaultLockfiles maps ecosystem keys to their default lockfile labels.
var defaultLockfiles = map[string]string{
	"pip":   "//bazel/requirements:all.txt",
	"pnpm":  "//:pnpm-lock.yaml",
	"gomod": "//:go.sum",
}

// defaultScaRules maps ecosystem keys to per-ecosystem SCA rule labels.
var defaultScaRules = map[string]string{
	"pip":   "//bazel/semgrep/rules:sca_python_rules",
	"pnpm":  "//bazel/semgrep/rules:sca_javascript_rules",
	"gomod": "//bazel/semgrep/rules:sca_golang_rules",
}

// detectLockfiles inspects a target's deps for external dependency prefixes
// and returns the matching lockfile labels from the config.
func detectLockfiles(target *rule.Rule, cfg *semgrepConfig) []string {
	if !cfg.scaEnabled || len(cfg.lockfiles) == 0 {
		return nil
	}

	deps := target.AttrStrings("deps")
	ecosystems := make(map[string]bool)

	for _, dep := range deps {
		for prefix, ecosystem := range depPrefixToEcosystem {
			if strings.HasPrefix(dep, prefix) {
				ecosystems[ecosystem] = true
				break
			}
		}
	}

	var lockfiles []string
	for ecosystem := range ecosystems {
		if label, ok := cfg.lockfiles[ecosystem]; ok {
			lockfiles = append(lockfiles, label)
		}
	}

	sort.Strings(lockfiles)
	return lockfiles
}

// detectScaRules returns the SCA rule labels for ecosystems detected in a target's deps.
func detectScaRules(target *rule.Rule, cfg *semgrepConfig) []string {
	if !cfg.scaEnabled || len(cfg.scaRules) == 0 {
		return nil
	}

	deps := target.AttrStrings("deps")
	ecosystems := make(map[string]bool)

	for _, dep := range deps {
		for prefix, ecosystem := range depPrefixToEcosystem {
			if strings.HasPrefix(dep, prefix) {
				ecosystems[ecosystem] = true
				break
			}
		}
	}

	var rules []string
	for ecosystem := range ecosystems {
		if label, ok := cfg.scaRules[ecosystem]; ok {
			rules = append(rules, label)
		}
	}

	sort.Strings(rules)
	return rules
}

// copyLockfiles creates a shallow copy of a lockfiles map.
func copyLockfiles(src map[string]string) map[string]string {
	if src == nil {
		return nil
	}
	dst := make(map[string]string, len(src))
	for k, v := range src {
		dst[k] = v
	}
	return dst
}

// copyScaRules creates a shallow copy of a scaRules map.
func copyScaRules(src map[string]string) map[string]string {
	if src == nil {
		return nil
	}
	dst := make(map[string]string, len(src))
	for k, v := range src {
		dst[k] = v
	}
	return dst
}
