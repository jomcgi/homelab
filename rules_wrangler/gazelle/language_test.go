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

	_, ok := lang.(*wranglerLang)
	if !ok {
		t.Error("NewLanguage() should return *wranglerLang")
	}
}

func TestWranglerLang_Name(t *testing.T) {
	lang := NewLanguage()
	name := lang.Name()

	if name != languageName {
		t.Errorf("Name() = %q, want %q", name, languageName)
	}
	if name != "wrangler" {
		t.Errorf("Name() = %q, want %q", name, "wrangler")
	}
}

func TestWranglerLang_KnownDirectives(t *testing.T) {
	lang := NewLanguage()
	directives := lang.KnownDirectives()

	expected := []string{
		"wrangler",
		"wrangler_enabled",
		"wrangler_dist",
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

func TestWranglerLang_Kinds(t *testing.T) {
	lang := NewLanguage()
	kinds := lang.Kinds()

	wp, ok := kinds["wrangler_pages"]
	if !ok {
		t.Fatal("Kinds() missing wrangler_pages")
	}

	// Check NonEmptyAttrs
	nonEmptyExpected := []string{"dist", "project_name", "wrangler"}
	for _, attr := range nonEmptyExpected {
		if !wp.NonEmptyAttrs[attr] {
			t.Errorf("wrangler_pages should have %s as non-empty attr", attr)
		}
	}

	// Check MergeableAttrs
	if !wp.MergeableAttrs["visibility"] {
		t.Error("wrangler_pages should have visibility as mergeable attr")
	}
}

func TestWranglerLang_Loads(t *testing.T) {
	lang := NewLanguage()
	loads := lang.Loads()

	if len(loads) != 1 {
		t.Fatalf("Loads() returned %d loads, want 1", len(loads))
	}

	load := loads[0]
	if load.Name != "//rules_wrangler:defs.bzl" {
		t.Errorf("Loads()[0].Name = %q, want %q", load.Name, "//rules_wrangler:defs.bzl")
	}

	found := false
	for _, s := range load.Symbols {
		if s == "wrangler_pages" {
			found = true
			break
		}
	}
	if !found {
		t.Error("defs.bzl should export wrangler_pages symbol")
	}
}

func TestWranglerLang_CheckFlags(t *testing.T) {
	lang := NewLanguage()
	err := lang.CheckFlags(nil, nil)
	if err != nil {
		t.Errorf("CheckFlags() returned error: %v", err)
	}
}

func TestWranglerLang_Imports(t *testing.T) {
	lang := NewLanguage()
	imports := lang.Imports(nil, nil, nil)

	if imports != nil {
		t.Errorf("Imports() should return nil, got %v", imports)
	}
}

func TestWranglerLang_Embeds(t *testing.T) {
	lang := &wranglerLang{}
	embeds := lang.Embeds(nil, label.Label{})

	if embeds != nil {
		t.Errorf("Embeds() should return nil, got %v", embeds)
	}
}
