// Package gazelle provides a Gazelle extension for auto-generating BUILD files
// with semgrep_test targets for Python packages.
package gazelle

import (
	"flag"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/label"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/repo"
	"github.com/bazelbuild/bazel-gazelle/resolve"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

const languageName = "semgrep"

// NewLanguage creates a new instance of the semgrep Gazelle language.
func NewLanguage() language.Language {
	return &semgrepLang{}
}

type semgrepLang struct{}

// Name returns the name of this language extension.
func (l *semgrepLang) Name() string {
	return languageName
}

// RegisterFlags registers command-line flags for this extension.
func (l *semgrepLang) RegisterFlags(fs *flag.FlagSet, cmd string, c *config.Config) {
	// No custom flags needed
}

// CheckFlags validates command-line flags.
func (l *semgrepLang) CheckFlags(fs *flag.FlagSet, c *config.Config) error {
	return nil
}

// KnownDirectives returns the list of directives that this extension recognizes.
func (l *semgrepLang) KnownDirectives() []string {
	return []string{
		"semgrep",
		"semgrep_exclude_rules",
		"semgrep_target_kinds",
		"semgrep_languages",
		"semgrep_sca",
		"semgrep_sca_rules",
		"semgrep_lockfile",
	}
}

// Configure reads configuration from directives and command-line flags.
func (l *semgrepLang) Configure(c *config.Config, rel string, f *rule.File) {
	configure(c, rel, f)
}

// Kinds returns the list of rule kinds that this extension can generate.
func (l *semgrepLang) Kinds() map[string]rule.KindInfo {
	return map[string]rule.KindInfo{
		"semgrep_test": {
			MatchAny: false,
			NonEmptyAttrs: map[string]bool{
				"srcs":  true,
				"rules": true,
			},
			MergeableAttrs: map[string]bool{
				"srcs":          true,
				"rules":         true,
				"exclude_rules": true,
				"lockfiles":     true,
				"sca_rules":     true,
			},
		},
		"semgrep_target_test": {
			MatchAny: false,
			NonEmptyAttrs: map[string]bool{
				"target": true,
				"rules":  true,
			},
			MergeableAttrs: map[string]bool{
				"target":        true,
				"rules":         true,
				"exclude_rules": true,
				"lockfiles":     true,
				"sca_rules":     true,
			},
		},
	}
}

// Loads returns the list of labels that this extension may load.
func (l *semgrepLang) Loads() []rule.LoadInfo {
	return []rule.LoadInfo{
		{
			Name:    "//rules_semgrep:defs.bzl",
			Symbols: []string{"semgrep_test", "semgrep_target_test"},
		},
	}
}

// GenerateRules generates Bazel rules for semgrep tests.
func (l *semgrepLang) GenerateRules(args language.GenerateArgs) language.GenerateResult {
	return generateRules(args)
}

// Fix applies automated fixes to existing rules.
func (l *semgrepLang) Fix(c *config.Config, f *rule.File) {
	// No automated fixes needed
}

// Imports extracts import information from rules (not applicable for semgrep).
func (l *semgrepLang) Imports(c *config.Config, r *rule.Rule, f *rule.File) []resolve.ImportSpec {
	return nil
}

// Embeds extracts embed information from rules (not applicable for semgrep).
func (l *semgrepLang) Embeds(r *rule.Rule, from label.Label) []label.Label {
	return nil
}

// Resolve translates import paths to Bazel labels (not applicable for semgrep).
func (l *semgrepLang) Resolve(c *config.Config, ix *resolve.RuleIndex, rc *repo.RemoteCache, r *rule.Rule, imports interface{}, from label.Label) {
	// No resolution needed
}
