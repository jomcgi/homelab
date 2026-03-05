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
	"pip":   "//requirements:all.txt",
	"pnpm":  "//:pnpm-lock.yaml",
	"gomod": "//:go.sum",
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
