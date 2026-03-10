package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

func TestGetSemgrepConfig_Defaults(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	cfg := getSemgrepConfig(c)

	if !cfg.enabled {
		t.Error("expected enabled to be true by default")
	}
	if len(cfg.excludeRules) != 0 {
		t.Errorf("expected excludeRules to be empty by default, got %v", cfg.excludeRules)
	}

	// Default targetKinds: py_venv_binary → "", go_binary → ""
	if len(cfg.targetKinds) != 2 {
		t.Fatalf("expected 2 default targetKinds, got %d: %v", len(cfg.targetKinds), cfg.targetKinds)
	}
	if attr, ok := cfg.targetKinds["py_venv_binary"]; !ok || attr != "" {
		t.Errorf("expected targetKinds[py_venv_binary]=\"\", got ok=%v attr=%q", ok, attr)
	}
	if attr, ok := cfg.targetKinds["go_binary"]; !ok || attr != "" {
		t.Errorf("expected targetKinds[go_binary]=\"\", got ok=%v attr=%q", ok, attr)
	}

	// Default languages: ["py"]
	if len(cfg.languages) != 1 || cfg.languages[0] != "py" {
		t.Errorf("expected default languages=[py], got %v", cfg.languages)
	}
}

func TestGetSemgrepConfig_FromExtension(t *testing.T) {
	expected := &semgrepConfig{
		enabled:      false,
		excludeRules: []string{"rule1", "rule2"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: expected,
		},
	}

	cfg := getSemgrepConfig(c)

	if cfg != expected {
		t.Error("expected to return the stored config")
	}
	if cfg.enabled != expected.enabled {
		t.Errorf("expected enabled=%v, got %v", expected.enabled, cfg.enabled)
	}
	if len(cfg.excludeRules) != len(expected.excludeRules) {
		t.Errorf("expected excludeRules=%v, got %v", expected.excludeRules, cfg.excludeRules)
	}
}

func TestConfigure_Directives(t *testing.T) {
	tests := []struct {
		name             string
		directives       []rule.Directive
		parentConfig     *semgrepConfig
		wantEnabled      bool
		wantExcludeRules []string
	}{
		{
			name:             "no directives uses defaults",
			directives:       nil,
			parentConfig:     nil,
			wantEnabled:      true,
			wantExcludeRules: nil,
		},
		{
			name: "semgrep enabled directive",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "enabled"},
			},
			parentConfig:     nil,
			wantEnabled:      true,
			wantExcludeRules: nil,
		},
		{
			name: "semgrep disabled directive",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "disabled"},
			},
			parentConfig:     nil,
			wantEnabled:      false,
			wantExcludeRules: nil,
		},
		{
			name: "single exclude rule",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: "no-exec"},
			},
			parentConfig:     nil,
			wantEnabled:      true,
			wantExcludeRules: []string{"no-exec"},
		},
		{
			name: "multiple exclude rules",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: "no-exec, no-eval, no-import-os"},
			},
			parentConfig:     nil,
			wantEnabled:      true,
			wantExcludeRules: []string{"no-exec", "no-eval", "no-import-os"},
		},
		{
			name:       "inherits from parent",
			directives: nil,
			parentConfig: &semgrepConfig{
				enabled:      false,
				excludeRules: []string{"parent-rule"},
			},
			wantEnabled:      false,
			wantExcludeRules: []string{"parent-rule"},
		},
		{
			name: "child overrides parent enabled",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "enabled"},
			},
			parentConfig: &semgrepConfig{
				enabled:      false,
				excludeRules: []string{"parent-rule"},
			},
			wantEnabled:      true,
			wantExcludeRules: []string{"parent-rule"},
		},
		{
			name: "child overrides parent exclude rules",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: "child-rule"},
			},
			parentConfig: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"parent-rule"},
			},
			wantEnabled:      true,
			wantExcludeRules: []string{"child-rule"},
		},
		{
			name: "multiple directives combined",
			directives: []rule.Directive{
				{Key: "semgrep", Value: "disabled"},
				{Key: "semgrep_exclude_rules", Value: "rule-a,rule-b"},
			},
			parentConfig:     nil,
			wantEnabled:      false,
			wantExcludeRules: []string{"rule-a", "rule-b"},
		},
		{
			name: "empty exclude rules value",
			directives: []rule.Directive{
				{Key: "semgrep_exclude_rules", Value: ""},
			},
			parentConfig: &semgrepConfig{
				enabled:      true,
				excludeRules: []string{"parent-rule"},
			},
			wantEnabled:      true,
			wantExcludeRules: []string{"parent-rule"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			c := &config.Config{
				Exts: make(map[string]interface{}),
			}

			if tc.parentConfig != nil {
				c.Exts[semgrepConfigKey] = tc.parentConfig
			}

			var f *rule.File
			if tc.directives != nil {
				f = &rule.File{
					Directives: tc.directives,
				}
			}

			configure(c, "", f)

			cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

			if cfg.enabled != tc.wantEnabled {
				t.Errorf("enabled: got %v, want %v", cfg.enabled, tc.wantEnabled)
			}

			if len(cfg.excludeRules) != len(tc.wantExcludeRules) {
				t.Errorf("excludeRules: got %v (len %d), want %v (len %d)",
					cfg.excludeRules, len(cfg.excludeRules),
					tc.wantExcludeRules, len(tc.wantExcludeRules))
				return
			}

			for i, r := range cfg.excludeRules {
				if r != tc.wantExcludeRules[i] {
					t.Errorf("excludeRules[%d]: got %q, want %q", i, r, tc.wantExcludeRules[i])
				}
			}
		})
	}
}

func TestConfigure_NilFile(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	configure(c, "some/rel/path", nil)

	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if !cfg.enabled {
		t.Error("expected enabled to be true with nil file")
	}
}

func TestConfigure_ParentExcludeRulesNotMutated(t *testing.T) {
	parent := &semgrepConfig{
		enabled:      true,
		excludeRules: []string{"parent-rule"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: parent,
		},
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_exclude_rules", Value: "child-rule"},
		},
	}

	configure(c, "", f)

	// Verify parent was not mutated
	if len(parent.excludeRules) != 1 || parent.excludeRules[0] != "parent-rule" {
		t.Errorf("parent excludeRules was mutated: got %v", parent.excludeRules)
	}
}

// --- Tests for targetKinds directive ---

func TestParseTargetKinds(t *testing.T) {
	tests := []struct {
		name  string
		value string
		want  map[string]string
	}{
		{
			name:  "single kind without attr",
			value: "py_venv_binary",
			want:  map[string]string{"py_venv_binary": ""},
		},
		{
			name:  "single kind with attr",
			value: "py3_image=binary",
			want:  map[string]string{"py3_image": "binary"},
		},
		{
			name:  "multiple kinds mixed",
			value: "py_venv_binary,py3_image=binary",
			want:  map[string]string{"py_venv_binary": "", "py3_image": "binary"},
		},
		{
			name:  "spaces around entries",
			value: "py_venv_binary , py3_image=binary",
			want:  map[string]string{"py_venv_binary": "", "py3_image": "binary"},
		},
		{
			name:  "spaces around equals",
			value: "py3_image = binary",
			want:  map[string]string{"py3_image": "binary"},
		},
		{
			name:  "empty entries ignored",
			value: "py_venv_binary,,py3_image=binary,",
			want:  map[string]string{"py_venv_binary": "", "py3_image": "binary"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := parseTargetKinds(tc.value)
			if len(got) != len(tc.want) {
				t.Fatalf("parseTargetKinds(%q) = %v (len %d), want %v (len %d)",
					tc.value, got, len(got), tc.want, len(tc.want))
			}
			for kind, wantAttr := range tc.want {
				gotAttr, ok := got[kind]
				if !ok {
					t.Errorf("missing kind %q", kind)
					continue
				}
				if gotAttr != wantAttr {
					t.Errorf("kind %q: got attr %q, want %q", kind, gotAttr, wantAttr)
				}
			}
		})
	}
}

func TestParseLanguages(t *testing.T) {
	tests := []struct {
		name  string
		value string
		want  []string
	}{
		{
			name:  "single language",
			value: "py",
			want:  []string{"py"},
		},
		{
			name:  "multiple languages",
			value: "py,go",
			want:  []string{"py", "go"},
		},
		{
			name:  "spaces trimmed",
			value: "py , go",
			want:  []string{"py", "go"},
		},
		{
			name:  "empty entries ignored",
			value: "py,,go,",
			want:  []string{"py", "go"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := parseLanguages(tc.value)
			if len(got) != len(tc.want) {
				t.Fatalf("parseLanguages(%q) = %v, want %v", tc.value, got, tc.want)
			}
			for i, w := range tc.want {
				if got[i] != w {
					t.Errorf("[%d] got %q, want %q", i, got[i], w)
				}
			}
		})
	}
}

func TestConfigure_TargetKindsDirective(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_target_kinds", Value: "py_venv_binary,py3_image=binary"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if len(cfg.targetKinds) != 2 {
		t.Fatalf("expected 2 targetKinds, got %d: %v", len(cfg.targetKinds), cfg.targetKinds)
	}
	if attr, ok := cfg.targetKinds["py_venv_binary"]; !ok || attr != "" {
		t.Errorf("py_venv_binary: ok=%v attr=%q, want ok=true attr=\"\"", ok, attr)
	}
	if attr, ok := cfg.targetKinds["py3_image"]; !ok || attr != "binary" {
		t.Errorf("py3_image: ok=%v attr=%q, want ok=true attr=\"binary\"", ok, attr)
	}
}

func TestConfigure_LanguagesDirective(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_languages", Value: "py,go"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if len(cfg.languages) != 2 {
		t.Fatalf("expected 2 languages, got %d: %v", len(cfg.languages), cfg.languages)
	}
	if cfg.languages[0] != "py" || cfg.languages[1] != "go" {
		t.Errorf("languages = %v, want [py go]", cfg.languages)
	}
}

func TestConfigure_TargetKindsInheritance(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
		targetKinds: map[string]string{"py_venv_binary": "", "py3_image": "binary"},
		languages:   []string{"py", "go"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: parent,
		},
	}

	// Child has no directives — should inherit parent's targetKinds and languages
	configure(c, "sub/dir", nil)

	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if len(cfg.targetKinds) != 2 {
		t.Fatalf("expected 2 inherited targetKinds, got %d: %v", len(cfg.targetKinds), cfg.targetKinds)
	}
	if _, ok := cfg.targetKinds["py3_image"]; !ok {
		t.Error("expected py3_image to be inherited")
	}
	if len(cfg.languages) != 2 {
		t.Fatalf("expected 2 inherited languages, got %d: %v", len(cfg.languages), cfg.languages)
	}
}

func TestConfigure_TargetKindsChildOverridesParent(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
		targetKinds: map[string]string{"py_venv_binary": "", "py3_image": "binary"},
		languages:   []string{"py", "go"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: parent,
		},
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_target_kinds", Value: "py_venv_binary"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	// Child should have only py_venv_binary, not py3_image
	if len(cfg.targetKinds) != 1 {
		t.Fatalf("expected 1 targetKind after override, got %d: %v", len(cfg.targetKinds), cfg.targetKinds)
	}
	if _, ok := cfg.targetKinds["py_venv_binary"]; !ok {
		t.Error("expected py_venv_binary in overridden config")
	}
	if _, ok := cfg.targetKinds["py3_image"]; ok {
		t.Error("py3_image should not be in overridden config")
	}

	// Languages should still be inherited
	if len(cfg.languages) != 2 {
		t.Errorf("languages should be inherited, got %v", cfg.languages)
	}
}

func TestConfigure_ParentTargetKindsNotMutated(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
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
			{Key: "semgrep_target_kinds", Value: "py3_image=binary"},
		},
	}

	configure(c, "", f)

	// Verify parent was not mutated
	if len(parent.targetKinds) != 1 {
		t.Errorf("parent targetKinds was mutated: got %v", parent.targetKinds)
	}
	if _, ok := parent.targetKinds["py_venv_binary"]; !ok {
		t.Error("parent should still have py_venv_binary")
	}
}

func TestConfigure_EmptyTargetKindsValueKeepsParent(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
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
			{Key: "semgrep_target_kinds", Value: ""},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	// Empty value should not override parent
	if len(cfg.targetKinds) != 1 {
		t.Errorf("expected parent targetKinds preserved, got %v", cfg.targetKinds)
	}
}

// --- Tests for SCA config directives ---

func TestConfigure_SCADirectives(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_sca", Value: "disabled"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if cfg.scaEnabled {
		t.Error("expected scaEnabled to be false after disabled directive")
	}
}

func TestConfigure_SCADefaults(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	cfg := getSemgrepConfig(c)

	if !cfg.scaEnabled {
		t.Error("expected scaEnabled to be true by default")
	}
	if len(cfg.scaRules) != 3 {
		t.Errorf("expected 3 default scaRules, got %d: %v", len(cfg.scaRules), cfg.scaRules)
	}
	if cfg.scaRules["pip"] != "//bazel/semgrep/rules:sca_python_rules" {
		t.Errorf("expected pip scaRules, got %q", cfg.scaRules["pip"])
	}
	if cfg.scaRules["pnpm"] != "//bazel/semgrep/rules:sca_javascript_rules" {
		t.Errorf("expected pnpm scaRules, got %q", cfg.scaRules["pnpm"])
	}
	if cfg.scaRules["gomod"] != "//bazel/semgrep/rules:sca_golang_rules" {
		t.Errorf("expected gomod scaRules, got %q", cfg.scaRules["gomod"])
	}
	if len(cfg.lockfiles) != 3 {
		t.Errorf("expected 3 default lockfiles, got %d: %v", len(cfg.lockfiles), cfg.lockfiles)
	}
}

func TestConfigure_SCALockfileDirective(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_lockfile", Value: "pip //requirements:custom.txt"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if cfg.lockfiles["pip"] != "//bazel/requirements:custom.txt" {
		t.Errorf("expected pip lockfile override, got %q", cfg.lockfiles["pip"])
	}
}

func TestConfigure_SCARulesDirective(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	f := &rule.File{
		Directives: []rule.Directive{
			{Key: "semgrep_sca_rules", Value: "pip //custom:sca_rules"},
		},
	}

	configure(c, "", f)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if cfg.scaRules["pip"] != "//custom:sca_rules" {
		t.Errorf("expected custom pip scaRules, got %q", cfg.scaRules["pip"])
	}
}

func TestConfigure_SCAInheritance(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
		scaEnabled:  false,
		scaRules:    map[string]string{"pip": "//custom:sca"},
		lockfiles:   map[string]string{"pip": "//custom:req.txt"},
		targetKinds: map[string]string{"py_venv_binary": ""},
		languages:   []string{"py"},
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: parent,
		},
	}

	configure(c, "sub/dir", nil)
	cfg := c.Exts[semgrepConfigKey].(*semgrepConfig)

	if cfg.scaEnabled {
		t.Error("scaEnabled should be inherited as false")
	}
	if cfg.scaRules["pip"] != "//custom:sca" {
		t.Errorf("scaRules should be inherited, got %v", cfg.scaRules)
	}
	if cfg.lockfiles["pip"] != "//custom:req.txt" {
		t.Errorf("lockfiles should be inherited, got %v", cfg.lockfiles)
	}
}

func TestConfigure_SCALockfileParentNotMutated(t *testing.T) {
	parent := &semgrepConfig{
		enabled:     true,
		scaEnabled:  true,
		scaRules:    copyScaRules(defaultScaRules),
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
			{Key: "semgrep_lockfile", Value: "pip //requirements:custom.txt"},
		},
	}

	configure(c, "", f)

	if parent.lockfiles["pip"] != "//req:all.txt" {
		t.Errorf("parent lockfiles was mutated: got %v", parent.lockfiles)
	}
}

func TestCopyTargetKinds(t *testing.T) {
	src := map[string]string{"a": "1", "b": "2"}
	dst := copyTargetKinds(src)

	// Modify dst, verify src unchanged
	dst["c"] = "3"
	if _, ok := src["c"]; ok {
		t.Error("modifying copy should not affect original")
	}

	// Nil input
	if copyTargetKinds(nil) != nil {
		t.Error("copyTargetKinds(nil) should return nil")
	}
}
