package gazelle

import (
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// binaryKinds are the rule kinds that represent Python binary entry points.
var binaryKinds = map[string]bool{
	"py_venv_binary": true,
	"py_binary":      true,
}

// libraryKinds are the rule kinds that represent Python libraries.
var libraryKinds = map[string]bool{
	"py_library": true,
}

// generateRules generates semgrep test targets for a package.
//
// When py_venv_binary or py_binary targets exist in the BUILD file:
//   - Generates one semgrep_target_test per binary (aspect scans transitive deps)
//   - Generates per-file semgrep_test only for orphan .py files not covered by any
//     binary's transitive local deps (files that the aspect won't scan)
//
// When no binaries exist, falls back to per-file semgrep_test for every .py file.
func generateRules(args language.GenerateArgs) language.GenerateResult {
	cfg := getSemgrepConfig(args.Config)

	var result language.GenerateResult

	if !cfg.enabled {
		return result
	}

	pyFiles := pythonFiles(args.RegularFiles)
	if len(pyFiles) == 0 {
		result.Empty = staleRules(args, nil)
		return result
	}

	// Detect binary targets in the existing BUILD file
	binaries := findBinaries(args.File)

	if len(binaries) > 0 {
		// Build the set of .py files covered by binaries' transitive local deps.
		// The aspect will scan these files, so they don't need per-file tests.
		coveredFiles := coveredByBinaries(args.File, binaries)

		// Generate semgrep_target_test for each binary
		for _, b := range binaries {
			name := b.Name() + "_semgrep_test"
			r := rule.NewRule("semgrep_target_test", name)
			r.SetAttr("target", ":"+b.Name())
			r.SetAttr("rules", []string{"//semgrep_rules:python_rules"})
			if len(cfg.excludeRules) > 0 {
				r.SetAttr("exclude_rules", sortedExcludeRules(cfg.excludeRules))
			}
			result.Gen = append(result.Gen, r)
			result.Imports = append(result.Imports, nil)
		}

		// Generate per-file semgrep_test for orphan .py files
		for _, f := range pyFiles {
			if coveredFiles[f] {
				continue
			}
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
	} else {
		// No binaries — fall back to per-file semgrep_test
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
	}

	result.Empty = staleRules(args, result.Gen)

	return result
}

// coveredByBinaries returns the set of .py files that are transitively reachable
// from the given binary targets through package-local deps. These files will be
// scanned by the semgrep aspect and don't need individual semgrep_test targets.
func coveredByBinaries(f *rule.File, binaries []*rule.Rule) map[string]bool {
	if f == nil {
		return nil
	}

	// Index: target name -> rule
	ruleByName := make(map[string]*rule.Rule)
	for _, r := range f.Rules {
		ruleByName[r.Name()] = r
	}

	// Index: target name -> srcs
	srcsByName := make(map[string][]string)
	for _, r := range f.Rules {
		if binaryKinds[r.Kind()] || libraryKinds[r.Kind()] {
			srcsByName[r.Name()] = r.AttrStrings("srcs")
		}
	}

	covered := make(map[string]bool)
	visited := make(map[string]bool)

	// Walk local deps from each binary, collecting all srcs
	for _, b := range binaries {
		walkLocalDeps(b, ruleByName, srcsByName, covered, visited)
	}

	return covered
}

// walkLocalDeps recursively collects .py srcs from a target and its
// package-local dependencies.
func walkLocalDeps(r *rule.Rule, ruleByName map[string]*rule.Rule, srcsByName map[string][]string, covered map[string]bool, visited map[string]bool) {
	name := r.Name()
	if visited[name] {
		return
	}
	visited[name] = true

	// Mark this target's srcs as covered
	if main := r.AttrString("main"); main != "" {
		covered[main] = true
	}
	for _, src := range srcsByName[name] {
		covered[src] = true
	}

	// Walk local deps (":foo" references)
	for _, dep := range r.AttrStrings("deps") {
		localName := localDepName(dep)
		if localName == "" {
			continue
		}
		depRule, ok := ruleByName[localName]
		if !ok {
			continue
		}
		walkLocalDeps(depRule, ruleByName, srcsByName, covered, visited)
	}
}

// localDepName extracts the target name from a package-local dep like ":foo".
// Returns "" for external or cross-package deps.
func localDepName(dep string) string {
	if strings.HasPrefix(dep, ":") {
		return dep[1:]
	}
	return ""
}

// findBinaries returns py_venv_binary and py_binary rules from the BUILD file.
func findBinaries(f *rule.File) []*rule.Rule {
	if f == nil {
		return nil
	}
	var binaries []*rule.Rule
	for _, r := range f.Rules {
		if binaryKinds[r.Kind()] {
			binaries = append(binaries, r)
		}
	}
	// Sort by name for deterministic output
	sort.Slice(binaries, func(i, j int) bool {
		return binaries[i].Name() < binaries[j].Name()
	})
	return binaries
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

// staleRules returns empty rules for existing semgrep_test and semgrep_target_test
// rules not in the generated set.
func staleRules(args language.GenerateArgs, gen []*rule.Rule) []*rule.Rule {
	if args.File == nil {
		return nil
	}

	active := make(map[string]bool)
	for _, r := range gen {
		active[r.Kind()+"/"+r.Name()] = true
	}

	var empty []*rule.Rule
	for _, r := range args.File.Rules {
		kind := r.Kind()
		if (kind == "semgrep_test" || kind == "semgrep_target_test") && !active[kind+"/"+r.Name()] {
			empty = append(empty, rule.NewRule(kind, r.Name()))
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
