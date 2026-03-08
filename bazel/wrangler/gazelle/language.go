// Package gazelle provides a Gazelle extension for auto-generating BUILD targets
// from wrangler.jsonc configuration files (Cloudflare Pages projects).
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

const languageName = "wrangler"

// NewLanguage creates a new instance of the wrangler Gazelle language.
func NewLanguage() language.Language {
	return &wranglerLang{}
}

type wranglerLang struct{}

// Name returns the name of this language extension.
func (l *wranglerLang) Name() string {
	return languageName
}

// RegisterFlags registers command-line flags for this extension.
func (l *wranglerLang) RegisterFlags(fs *flag.FlagSet, cmd string, c *config.Config) {
	// No custom flags needed
}

// CheckFlags validates command-line flags.
func (l *wranglerLang) CheckFlags(fs *flag.FlagSet, c *config.Config) error {
	return nil
}

// KnownDirectives returns the list of directives that this extension recognizes.
func (l *wranglerLang) KnownDirectives() []string {
	return []string{
		"wrangler",
		"wrangler_enabled",
		"wrangler_dist",
	}
}

// Configure reads configuration from directives and command-line flags.
func (l *wranglerLang) Configure(c *config.Config, rel string, f *rule.File) {
	configure(c, rel, f)
}

// Kinds returns the list of rule kinds that this extension can generate.
func (l *wranglerLang) Kinds() map[string]rule.KindInfo {
	return map[string]rule.KindInfo{
		"wrangler_pages": {
			MatchAny: false,
			NonEmptyAttrs: map[string]bool{
				"dist":         true,
				"project_name": true,
				"wrangler":     true,
			},
			MergeableAttrs: map[string]bool{
				"visibility": true,
			},
		},
	}
}

// Loads returns the list of labels that this extension may load.
func (l *wranglerLang) Loads() []rule.LoadInfo {
	return []rule.LoadInfo{
		{
			Name:    "//bazel/wrangler:defs.bzl",
			Symbols: []string{"wrangler_pages"},
		},
	}
}

// GenerateRules generates Bazel rules for wrangler_pages targets.
func (l *wranglerLang) GenerateRules(args language.GenerateArgs) language.GenerateResult {
	return generateRules(args)
}

// Fix applies automated fixes to existing rules.
func (l *wranglerLang) Fix(c *config.Config, f *rule.File) {
	// No automated fixes needed
}

// Imports extracts import information from rules (not applicable for wrangler).
func (l *wranglerLang) Imports(c *config.Config, r *rule.Rule, f *rule.File) []resolve.ImportSpec {
	return nil
}

// Embeds extracts embed information from rules (not applicable for wrangler).
func (l *wranglerLang) Embeds(r *rule.Rule, from label.Label) []label.Label {
	return nil
}

// Resolve translates import paths to Bazel labels (not applicable for wrangler).
func (l *wranglerLang) Resolve(c *config.Config, ix *resolve.RuleIndex, rc *repo.RemoteCache, r *rule.Rule, imports interface{}, from label.Label) {
	// No resolution needed
}
