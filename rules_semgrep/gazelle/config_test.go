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
