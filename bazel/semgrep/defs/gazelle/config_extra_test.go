package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// TestConfigure_SCAGlobalRulesOverride verifies that a semgrep_sca_rules
// directive with a single-part value (no space) overrides ALL ecosystem
// keys in scaRules with the given label.
func TestConfigure_SCAGlobalRulesOverride(t *testing.T) {
	// Start with default config which has 3 ecosystems: pip, pnpm, gomod
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_sca_rules", Value: "//custom:all_sca_rules"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	// All keys should be overridden with the global label
	for ecosystem, label := range cfg.scaRules {
		if label != "//custom:all_sca_rules" {
			t.Errorf("scaRules[%q] = %q, want //custom:all_sca_rules", ecosystem, label)
		}
	}

	// Should still have all 3 ecosystems
	if len(cfg.scaRules) != 3 {
		t.Errorf("expected 3 scaRules ecosystems after global override, got %d: %v", len(cfg.scaRules), cfg.scaRules)
	}
}

// TestConfigure_SCAGlobalRulesOverride_EmptyScaRules verifies that a global
// SCA rules override on an empty scaRules map is a no-op (no panic).
func TestConfigure_SCAGlobalRulesOverride_EmptyScaRules(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:     true,
				scaEnabled:  true,
				scaRules:    map[string]string{}, // empty
				lockfiles:   map[string]string{},
				targetKinds: map[string]string{"py_venv_binary": ""},
				languages:   []string{"py"},
			},
		},
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_sca_rules", Value: "//custom:all_sca_rules"},
		},
	}

	// Should not panic with empty scaRules
	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if len(cfg.scaRules) != 0 {
		t.Errorf("expected empty scaRules unchanged, got %v", cfg.scaRules)
	}
}

// TestConfigure_SCALockfileSinglePartIgnored verifies that a semgrep_lockfile
// directive with only one part (no space separator) is silently ignored —
// the existing lockfile config is preserved unchanged.
func TestConfigure_SCALockfileSinglePartIgnored(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:     true,
				scaEnabled:  true,
				scaRules:    copyScaRules(defaultScaRules),
				lockfiles:   map[string]string{"pip": "//original:req.txt"},
				targetKinds: map[string]string{"py_venv_binary": ""},
				languages:   []string{"py"},
			},
		},
	}

	f := &rule.File{
		Directives: []rule.Directive{
			// Missing space between ecosystem and label — malformed directive
			{Key: "semgrep_lockfile", Value: "//no-ecosystem-prefix:req.txt"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	// Original pip lockfile should be unchanged
	if cfg.lockfiles["pip"] != "//original:req.txt" {
		t.Errorf("lockfiles[pip] = %q, want //original:req.txt (single-part directive should be ignored)",
			cfg.lockfiles["pip"])
	}
}

// TestParseTargetKinds_EmptyKind verifies that an entry of the form "=attr"
// (empty kind before "=") is skipped and not added to the result.
func TestParseTargetKinds_EmptyKind(t *testing.T) {
	got := parseTargetKinds("=binary")

	if len(got) != 0 {
		t.Errorf("parseTargetKinds(\"=binary\") = %v, want empty map (empty kind should be skipped)", got)
	}
}

// TestParseTargetKinds_EmptyAttr verifies that an entry of the form "kind="
// (empty attr after "=") is stored with an empty attr value.
func TestParseTargetKinds_EmptyAttr(t *testing.T) {
	got := parseTargetKinds("my_kind=")

	if len(got) != 1 {
		t.Fatalf("parseTargetKinds(\"my_kind=\") = %v, want 1 entry", got)
	}
	attr, ok := got["my_kind"]
	if !ok {
		t.Fatal("expected key my_kind in result")
	}
	if attr != "" {
		t.Errorf("parseTargetKinds(\"my_kind=\") attr = %q, want \"\"", attr)
	}
}

// TestParseTargetKinds_JustEquals verifies that the entry "=" is skipped
// (both kind and attr are empty).
func TestParseTargetKinds_JustEquals(t *testing.T) {
	got := parseTargetKinds("=")

	if len(got) != 0 {
		t.Errorf("parseTargetKinds(\"=\") = %v, want empty map", got)
	}
}

// TestParseTargetKinds_MixedWithMalformed verifies that malformed entries are
// skipped while valid entries are still parsed correctly.
func TestParseTargetKinds_MixedWithMalformed(t *testing.T) {
	got := parseTargetKinds("py_venv_binary,=attr,go_binary=,valid_kind=something")

	// "=attr" should be skipped (empty kind)
	// "go_binary=" should be stored with empty attr
	// "valid_kind=something" should be stored normally
	// "py_venv_binary" should be stored with empty attr
	want := map[string]string{
		"py_venv_binary": "",
		"go_binary":      "",
		"valid_kind":     "something",
	}

	if len(got) != len(want) {
		t.Fatalf("parseTargetKinds returned %v (len %d), want %v (len %d)", got, len(got), want, len(want))
	}

	for k, wantAttr := range want {
		gotAttr, ok := got[k]
		if !ok {
			t.Errorf("missing key %q in result", k)
			continue
		}
		if gotAttr != wantAttr {
			t.Errorf("key %q: attr = %q, want %q", k, gotAttr, wantAttr)
		}
	}

	if _, ok := got["attr"]; ok {
		t.Error("key \"attr\" should not appear (was from malformed \"=attr\" entry)")
	}
}

// TestConfigure_SCAGlobalRulesOverride_ParentNotMutated verifies that using a
// global SCA rules override does not mutate the parent config's scaRules map.
func TestConfigure_SCAGlobalRulesOverride_ParentNotMutated(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
		scaEnabled:  true,
		scaRules:    map[string]string{"pip": "//original:pip_rules", "gomod": "//original:go_rules"},
		lockfiles:   map[string]string{"pip": "//req:all.txt"},
		targetKinds: map[string]string{"py_venv_binary": ""},
		languages:   []string{"py"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: parent,
		},
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_sca_rules", Value: "//custom:all_sca"},
		},
	}

	configure(c, "", f)

	// Parent scaRules must not be mutated
	if parent.scaRules["pip"] != "//original:pip_rules" {
		t.Errorf("parent scaRules[pip] was mutated: got %q", parent.scaRules["pip"])
	}
	if parent.scaRules["gomod"] != "//original:go_rules" {
		t.Errorf("parent scaRules[gomod] was mutated: got %q", parent.scaRules["gomod"])
	}

	// Child should have the override
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)
	if cfg.scaRules["pip"] != "//custom:all_sca" {
		t.Errorf("child scaRules[pip] = %q, want //custom:all_sca", cfg.scaRules["pip"])
	}
}
