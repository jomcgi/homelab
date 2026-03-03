package gazelle

import (
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// generateRules generates one semgrep_test per Python file in the package.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getSemgrepConfig(args.Config)

	var result language.GenerateResult

	if !cfg.enabled {
		return result
	}

	pyFiles := pythonFiles(args.RegularFiles)
	for _, f := range pyFiles {
		name := strings.TrimSuffix(f, ".py") + "_semgrep_test"
		r := rule.NewRule("semgrep_test", name)
		r.SetAttr("srcs", []string{f})
		r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})

		if len(cfg.excludeRules) > 0 {
			r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
		}

		result.Gen = append(result.Gen, r)
		result.Imports = append(result.Imports, nil)
	}

	// Mark stale semgrep_test rules for removal
	result.Empty = staleRules(args, result.Gen)

	return result
}

// pythonFiles returns the sorted subset of files that end with .py.
func pythonFiles(files []string) []string {
	var py []string
	for _, f := range files {
		if strings.HasSuffix(f, ".py") {
			py = append(py, f)
		}
	}
	sort.Strings(py)
	return py
}

// staleRules returns empty rules for existing semgrep_test rules not in the generated set.
func staleRules(args language.GenerateArgs, gen []*rule.Rule) []*rule.Rule {
	if args.File == nil {
		return nil
	}

	active := make(map[string]bool)
	for _, r := range gen {
		active[r.Name()] = true
	}

	var empty []*rule.Rule
	for _, r := range args.File.Rules {
		if r.Kind() == "semgrep_test" && !active[r.Name()] {
			empty = append(empty, rule.NewRule("semgrep_test", r.Name()))
		}
	}
	return empty
}

// sortedExcludeRules returns a sorted copy of the exclude rules list.
func sortedExcludeRules(rules []string) []string {
	sorted := append([]string{}, rules...)
	sort.Strings(sorted)
	return sorted
}
