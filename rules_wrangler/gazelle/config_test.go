package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

func TestGetWranglerConfig_Defaults(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	cfg := getWranglerConfig(c)

	if !cfg.enabled {
		t.Error("expected enabled to be true by default")
	}
	if cfg.dist != ":build_dist" {
		t.Errorf("expected dist to be ':build_dist', got %q", cfg.dist)
	}
}

func TestGetWranglerConfig_FromExtension(t *testing.T) {
	expected := &wranglerConfig{
		enabled: false,
		dist:    ":public",
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			wranglerConfigKey: expected,
		},
	}

	cfg := getWranglerConfig(c)

	if cfg != expected {
		t.Error("expected to return the stored config")
	}
	if cfg.enabled != expected.enabled {
		t.Errorf("expected enabled=%v, got %v", expected.enabled, cfg.enabled)
	}
	if cfg.dist != expected.dist {
		t.Errorf("expected dist=%q, got %q", expected.dist, cfg.dist)
	}
}

func TestConfigure_Directives(t *testing.T) {
	tests := []struct {
		name         string
		directives   []rule.Directive
		parentConfig *wranglerConfig
		wantEnabled  bool
		wantDist     string
	}{
		{
			name:         "no directives uses defaults",
			directives:   nil,
			parentConfig: nil,
			wantEnabled:  true,
			wantDist:     ":build_dist",
		},
		{
			name: "wrangler enabled directive",
			directives: []rule.Directive{
				{Key: "wrangler", Value: "enabled"},
			},
			parentConfig: nil,
			wantEnabled:  true,
			wantDist:     ":build_dist",
		},
		{
			name: "wrangler disabled directive",
			directives: []rule.Directive{
				{Key: "wrangler", Value: "disabled"},
			},
			parentConfig: nil,
			wantEnabled:  false,
			wantDist:     ":build_dist",
		},
		{
			name: "wrangler_enabled directive overrides parent",
			directives: []rule.Directive{
				{Key: "wrangler_enabled", Value: ""},
			},
			parentConfig: &wranglerConfig{
				enabled: false,
				dist:    ":build_dist",
			},
			wantEnabled: true,
			wantDist:    ":build_dist",
		},
		{
			name: "wrangler_dist directive",
			directives: []rule.Directive{
				{Key: "wrangler_dist", Value: ":public"},
			},
			parentConfig: nil,
			wantEnabled:  true,
			wantDist:     ":public",
		},
		{
			name: "multiple directives",
			directives: []rule.Directive{
				{Key: "wrangler_dist", Value: ":static"},
				{Key: "wrangler", Value: "enabled"},
			},
			parentConfig: nil,
			wantEnabled:  true,
			wantDist:     ":static",
		},
		{
			name: "inherits from parent",
			directives: []rule.Directive{
				{Key: "wrangler_dist", Value: ":custom"},
			},
			parentConfig: &wranglerConfig{
				enabled: false,
				dist:    ":parent_dist",
			},
			wantEnabled: false,
			wantDist:    ":custom",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			c := &config.Config{
				Exts: make(map[string]interface{}),
			}

			if tc.parentConfig != nil {
				c.Exts[wranglerConfigKey] = tc.parentConfig
			}

			var f *rule.File
			if tc.directives != nil {
				f = &rule.File{
					Directives: tc.directives,
				}
			}

			configure(c, "", f)

			cfg := c.Exts[wranglerConfigKey].(*wranglerConfig)

			if cfg.enabled != tc.wantEnabled {
				t.Errorf("enabled: got %v, want %v", cfg.enabled, tc.wantEnabled)
			}
			if cfg.dist != tc.wantDist {
				t.Errorf("dist: got %q, want %q", cfg.dist, tc.wantDist)
			}
		})
	}
}

func TestConfigure_NilFile(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	configure(c, "some/rel/path", nil)

	cfg := c.Exts[wranglerConfigKey].(*wranglerConfig)

	if !cfg.enabled {
		t.Error("expected enabled to be true with nil file")
	}
}
