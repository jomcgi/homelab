package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/label"
)

func TestNewLanguage(t *testing.T) {
	lang := NewLanguage()
	if lang == nil {
		t.Fatal("NewLanguage() returned nil")
	}

	_, ok := lang.(*semgrepLang)
	if !ok {
		t.Error("NewLanguage() should return *semgrepLang")
	}
}

func TestSemgrepLang_Name(t *testing.T) {
	lang := NewLanguage()
	name := lang.Name()

	if name != languageName {
		t.Errorf("Name() = %q, want %q", name, languageName)
	}
	if name != "semgrep" {
		t.Errorf("Name() = %q, want %q", name, "semgrep")
	}
}

func TestSemgrepLang_KnownDirectives(t *testing.T) {
	lang := NewLanguage()
	directives := lang.KnownDirectives()

	expected := []string{
		"semgrep",
		"semgrep_exclude_rules",
		"semgrep_target_kinds",
		"semgrep_languages",
		"semgrep_sca",
		"semgrep_sca_rules",
		"semgrep_lockfile",
	}

	if len(directives) != len(expected) {
		t.Errorf("KnownDirectives() returned %d directives, want %d", len(directives), len(expected))
	}

	directiveSet := make(map[string]bool)
	for _, d := range directives {
		directiveSet[d] = true
	}

	for _, e := range expected {
		if !directiveSet[e] {
			t.Errorf("KnownDirectives() missing directive %q", e)
		}
	}
}

func TestSemgrepLang_Kinds(t *testing.T) {
	lang := NewLanguage()
	kinds := lang.Kinds()

	expectedKinds := []string{"semgrep_test", "semgrep_target_test"}

	for _, k := range expectedKinds {
		if _, ok := kinds[k]; !ok {
			t.Errorf("Kinds() missing kind %q", k)
		}
	}
}

func TestSemgrepLang_Kinds_SemgrepTest(t *testing.T) {
	lang := NewLanguage()
	kinds := lang.Kinds()

	semgrepTest, ok := kinds["semgrep_test"]
	if !ok {
		t.Fatal("Kinds() missing semgrep_test")
	}

	if semgrepTest.MatchAny {
		t.Error("semgrep_test should have MatchAny=false")
	}

	// Check NonEmptyAttrs
	nonEmptyExpected := []string{"srcs", "rules"}
	for _, attr := range nonEmptyExpected {
		if !semgrepTest.NonEmptyAttrs[attr] {
			t.Errorf("semgrep_test should have %s as non-empty attr", attr)
		}
	}

	// Check MergeableAttrs
	mergeableExpected := []string{"exclude_rules"}
	for _, attr := range mergeableExpected {
		if !semgrepTest.MergeableAttrs[attr] {
			t.Errorf("semgrep_test should have %s as mergeable attr", attr)
		}
	}
}

func TestSemgrepLang_Kinds_SemgrepTargetTest(t *testing.T) {
	lang := NewLanguage()
	kinds := lang.Kinds()

	semgrepTargetTest, ok := kinds["semgrep_target_test"]
	if !ok {
		t.Fatal("Kinds() missing semgrep_target_test")
	}

	if semgrepTargetTest.MatchAny {
		t.Error("semgrep_target_test should have MatchAny=false")
	}

	// Check NonEmptyAttrs
	nonEmptyExpected := []string{"target", "rules"}
	for _, attr := range nonEmptyExpected {
		if !semgrepTargetTest.NonEmptyAttrs[attr] {
			t.Errorf("semgrep_target_test should have %s as non-empty attr", attr)
		}
	}

	// Check MergeableAttrs
	mergeableExpected := []string{"exclude_rules"}
	for _, attr := range mergeableExpected {
		if !semgrepTargetTest.MergeableAttrs[attr] {
			t.Errorf("semgrep_target_test should have %s as mergeable attr", attr)
		}
	}
}

func TestSemgrepLang_Loads(t *testing.T) {
	lang := NewLanguage()
	loads := lang.Loads()

	if len(loads) != 1 {
		t.Fatalf("Loads() returned %d loads, want 1", len(loads))
	}

	load := loads[0]
	if load.Name != "//bazel/semgrep/defs:defs.bzl" {
		t.Errorf("Loads()[0].Name = %q, want %q", load.Name, "//bazel/semgrep/defs:defs.bzl")
	}

	expectedSymbols := map[string]bool{"semgrep_test": true, "semgrep_target_test": true}
	for _, s := range load.Symbols {
		delete(expectedSymbols, s)
	}
	for missing := range expectedSymbols {
		t.Errorf("defs.bzl should export %q symbol", missing)
	}
}

func TestSemgrepLang_CheckFlags(t *testing.T) {
	lang := NewLanguage()
	err := lang.CheckFlags(nil, nil)
	if err != nil {
		t.Errorf("CheckFlags() returned error: %v", err)
	}
}

func TestSemgrepLang_Imports(t *testing.T) {
	lang := NewLanguage()
	imports := lang.Imports(nil, nil, nil)

	if imports != nil {
		t.Errorf("Imports() should return nil, got %v", imports)
	}
}

func TestSemgrepLang_Embeds(t *testing.T) {
	lang := &semgrepLang{}
	embeds := lang.Embeds(nil, label.Label{})

	if embeds != nil {
		t.Errorf("Embeds() should return nil, got %v", embeds)
	}
}

func TestSemgrepLang_RegisterFlags(t *testing.T) {
	// RegisterFlags is a no-op — calling it must not panic.
	lang := NewLanguage()
	lang.RegisterFlags(nil, "update", nil)
}

func TestSemgrepLang_Fix(t *testing.T) {
	// Fix is a no-op — calling it must not panic.
	lang := NewLanguage()
	lang.Fix(nil, nil)
}

func TestSemgrepLang_Resolve(t *testing.T) {
	// Resolve is a no-op — calling it must not panic.
	lang := NewLanguage()
	lang.Resolve(nil, nil, nil, nil, nil, label.Label{})
}
