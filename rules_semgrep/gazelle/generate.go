package gazelle

import (
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// generateRules generates semgrep_test BUILD rules for packages containing Python files.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getSemgrepConfig(args.Config)

	var result language.GenerateResult

	// Only generate rules if enabled
	if !cfg.enabled {
		return result
	}

	// Only generate if the package contains Python files
	if !hasPythonFiles(args.RegularFiles) {
		return result
	}

	r := rule.NewRule("semgrep_test", "semgrep_test")
	r.SetAttr("srcs", rule.GlobValue{
		Patterns: []string{"*.py"},
	})
	r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})

	if len(cfg.excludeRules) > 0 {
		r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
	}

	result.Gen = append(result.Gen, r)
	result.Imports = append(result.Imports, nil)

	return result
}

// hasPythonFiles returns true if any of the given files end with .py.
func hasPythonFiles(files []string) bool {
	for _, f := range files {
		if strings.HasSuffix(f, ".py") {
			return true
		}
	}
	return false
}

// sortedExcludeRules returns a sorted copy of the exclude rules list.
func sortedExcludeRules(rules []string) []string {
	sorted := append([]string{}, rules...)
	sort.Strings(sorted)
	return sorted
}
