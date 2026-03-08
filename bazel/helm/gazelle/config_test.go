package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

func TestGetArgoCDConfig_Defaults(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	cfg := getArgoCDConfig(c)

	if !cfg.enabled {
		t.Error("expected enabled to be true by default")
	}
	if cfg.generateDiff {
		t.Error("expected generateDiff to be false by default")
	}
	if !cfg.generateManifests {
		t.Error("expected generateManifests to be true by default")
	}
	if cfg.kubectlContext != "current" {
		t.Errorf("expected kubectlContext to be 'current', got %q", cfg.kubectlContext)
	}
}

func TestGetArgoCDConfig_FromExtension(t *testing.T) {
	expected := &argoCDConfig{
		enabled:           false,
		generateDiff:      true,
		generateManifests: false,
		kubectlContext:    "test-context",
	}

	c := &config.Config{
		Exts: map[string]interface{}{
			argoCDConfigKey: expected,
		},
	}

	cfg := getArgoCDConfig(c)

	if cfg != expected {
		t.Error("expected to return the stored config")
	}
	if cfg.enabled != expected.enabled {
		t.Errorf("expected enabled=%v, got %v", expected.enabled, cfg.enabled)
	}
	if cfg.generateDiff != expected.generateDiff {
		t.Errorf("expected generateDiff=%v, got %v", expected.generateDiff, cfg.generateDiff)
	}
	if cfg.generateManifests != expected.generateManifests {
		t.Errorf("expected generateManifests=%v, got %v", expected.generateManifests, cfg.generateManifests)
	}
	if cfg.kubectlContext != expected.kubectlContext {
		t.Errorf("expected kubectlContext=%q, got %q", expected.kubectlContext, cfg.kubectlContext)
	}
}

func TestConfigure_Directives(t *testing.T) {
	tests := []struct {
		name              string
		directives        []rule.Directive
		parentConfig      *argoCDConfig
		wantEnabled       bool
		wantGenerateDiff  bool
		wantGenerateManif bool
		wantKubectlCtx    string
	}{
		{
			name:              "no directives uses defaults",
			directives:        nil,
			parentConfig:      nil,
			wantEnabled:       true,
			wantGenerateDiff:  false,
			wantGenerateManif: true,
			wantKubectlCtx:    "current",
		},
		{
			name: "argocd enabled directive",
			directives: []rule.Directive{
				{Key: "argocd", Value: "enabled"},
			},
			parentConfig:      nil,
			wantEnabled:       true,
			wantGenerateDiff:  false,
			wantGenerateManif: true,
			wantKubectlCtx:    "current",
		},
		{
			name: "argocd disabled directive",
			directives: []rule.Directive{
				{Key: "argocd", Value: "disabled"},
			},
			parentConfig:      nil,
			wantEnabled:       false,
			wantGenerateDiff:  false,
			wantGenerateManif: true,
			wantKubectlCtx:    "current",
		},
		{
			name: "argocd_enabled directive",
			directives: []rule.Directive{
				{Key: "argocd_enabled", Value: ""},
			},
			parentConfig: &argoCDConfig{
				enabled:           false,
				generateDiff:      false,
				generateManifests: true,
				kubectlContext:    "current",
			},
			wantEnabled:       true,
			wantGenerateDiff:  false,
			wantGenerateManif: true,
			wantKubectlCtx:    "current",
		},
		{
			name: "argocd_generate_diff true",
			directives: []rule.Directive{
				{Key: "argocd_generate_diff", Value: "true"},
			},
			parentConfig:      nil,
			wantEnabled:       true,
			wantGenerateDiff:  true,
			wantGenerateManif: true,
			wantKubectlCtx:    "current",
		},
		{
			name: "argocd_generate_diff false",
			directives: []rule.Directive{
				{Key: "argocd_generate_diff", Value: "false"},
			},
			parentConfig: &argoCDConfig{
				enabled:           true,
				generateDiff:      true,
				generateManifests: true,
				kubectlContext:    "current",
			},
			wantEnabled:       true,
			wantGenerateDiff:  false,
			wantGenerateManif: true,
			wantKubectlCtx:    "current",
		},
		{
			name: "argocd_generate_manifests false",
			directives: []rule.Directive{
				{Key: "argocd_generate_manifests", Value: "false"},
			},
			parentConfig:      nil,
			wantEnabled:       true,
			wantGenerateDiff:  false,
			wantGenerateManif: false,
			wantKubectlCtx:    "current",
		},
		{
			name: "kubectl_context directive",
			directives: []rule.Directive{
				{Key: "kubectl_context", Value: "homelab"},
			},
			parentConfig:      nil,
			wantEnabled:       true,
			wantGenerateDiff:  false,
			wantGenerateManif: true,
			wantKubectlCtx:    "homelab",
		},
		{
			name: "multiple directives",
			directives: []rule.Directive{
				{Key: "argocd_generate_diff", Value: "true"},
				{Key: "argocd_generate_manifests", Value: "false"},
				{Key: "kubectl_context", Value: "prod"},
			},
			parentConfig:      nil,
			wantEnabled:       true,
			wantGenerateDiff:  true,
			wantGenerateManif: false,
			wantKubectlCtx:    "prod",
		},
		{
			name: "inherits from parent",
			directives: []rule.Directive{
				{Key: "argocd_generate_diff", Value: "true"},
			},
			parentConfig: &argoCDConfig{
				enabled:           true,
				generateDiff:      false,
				generateManifests: false,
				kubectlContext:    "parent-ctx",
			},
			wantEnabled:       true,
			wantGenerateDiff:  true,
			wantGenerateManif: false,
			wantKubectlCtx:    "parent-ctx",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			c := &config.Config{
				Exts: make(map[string]interface{}),
			}

			if tc.parentConfig != nil {
				c.Exts[argoCDConfigKey] = tc.parentConfig
			}

			var f *rule.File
			if tc.directives != nil {
				f = &rule.File{
					Directives: tc.directives,
				}
			}

			configure(c, "", f)

			cfg := c.Exts[argoCDConfigKey].(*argoCDConfig)

			if cfg.enabled != tc.wantEnabled {
				t.Errorf("enabled: got %v, want %v", cfg.enabled, tc.wantEnabled)
			}
			if cfg.generateDiff != tc.wantGenerateDiff {
				t.Errorf("generateDiff: got %v, want %v", cfg.generateDiff, tc.wantGenerateDiff)
			}
			if cfg.generateManifests != tc.wantGenerateManif {
				t.Errorf("generateManifests: got %v, want %v", cfg.generateManifests, tc.wantGenerateManif)
			}
			if cfg.kubectlContext != tc.wantKubectlCtx {
				t.Errorf("kubectlContext: got %q, want %q", cfg.kubectlContext, tc.wantKubectlCtx)
			}
		})
	}
}

func TestConfigure_NilFile(t *testing.T) {
	c := &config.Config{
		Exts: make(map[string]interface{}),
	}

	configure(c, "some/rel/path", nil)

	cfg := c.Exts[argoCDConfigKey].(*argoCDConfig)

	if !cfg.enabled {
		t.Error("expected enabled to be true with nil file")
	}
}
