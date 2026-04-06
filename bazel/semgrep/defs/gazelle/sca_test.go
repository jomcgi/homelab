package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/rule"
)

// ---------------------------------------------------------------------------
// detectLockfiles – edge cases not already covered by TestDetectLockfiles in
// generate_test.go (which covers happy-path pip/go/pnpm detection).
// ---------------------------------------------------------------------------

func TestDetectLockfiles_EmptyDeps(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	// No deps attr set at all.

	cfg := &semgrepConfig{
		scaEnabled: true,
		lockfiles:  map[string]string{"pip": "//bazel/requirements:all.txt"},
	}

	got := detectLockfiles(r, cfg)
	if len(got) != 0 {
		t.Errorf("detectLockfiles() with no deps = %v, want nil/empty", got)
	}
}

func TestDetectLockfiles_EmptyLockfilesMap(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{"@pip//requests"})

	cfg := &semgrepConfig{
		scaEnabled: true,
		lockfiles:  map[string]string{}, // empty map
	}

	got := detectLockfiles(r, cfg)
	if len(got) != 0 {
		t.Errorf("detectLockfiles() with empty lockfiles map = %v, want nil/empty", got)
	}
}

func TestDetectLockfiles_ScaDisabledWithEmptyLockfiles(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{"@pip//requests"})

	cfg := &semgrepConfig{
		scaEnabled: false,
		lockfiles:  map[string]string{}, // disabled AND empty
	}

	got := detectLockfiles(r, cfg)
	if got != nil {
		t.Errorf("detectLockfiles() with scaEnabled=false = %v, want nil", got)
	}
}

func TestDetectLockfiles_AllThreeEcosystems(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{
		"@pip//requests",
		"@npm//react",
		"@go_deps//example.com/pkg",
	})

	cfg := &semgrepConfig{
		scaEnabled: true,
		lockfiles: map[string]string{
			"pip":   "//bazel/requirements:all.txt",
			"pnpm":  "//:pnpm-lock.yaml",
			"gomod": "//:go.sum",
		},
	}

	got := detectLockfiles(r, cfg)
	if len(got) != 3 {
		t.Fatalf("detectLockfiles() = %v (len %d), want 3 lockfiles", got, len(got))
	}
	// Results are sorted; verify the exact sorted order.
	want := []string{"//:go.sum", "//:pnpm-lock.yaml", "//bazel/requirements:all.txt"}
	for i, w := range want {
		if got[i] != w {
			t.Errorf("[%d] = %q, want %q", i, got[i], w)
		}
	}
}

func TestDetectLockfiles_DuplicateEcosystemDepsDeduped(t *testing.T) {
	// Multiple @pip// deps should still yield exactly one lockfile for pip.
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{
		"@pip//requests",
		"@pip//flask",
		"@pip//sqlalchemy",
	})

	cfg := &semgrepConfig{
		scaEnabled: true,
		lockfiles:  map[string]string{"pip": "//bazel/requirements:all.txt"},
	}

	got := detectLockfiles(r, cfg)
	if len(got) != 1 {
		t.Fatalf("detectLockfiles() = %v, want exactly 1 lockfile (deduped)", got)
	}
	if got[0] != "//bazel/requirements:all.txt" {
		t.Errorf("lockfile[0] = %q, want //bazel/requirements:all.txt", got[0])
	}
}

func TestDetectLockfiles_OnlyLocalDeps(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{":local_lib", "//other:target", "//services/foo:bar"})

	cfg := &semgrepConfig{
		scaEnabled: true,
		lockfiles:  map[string]string{"pip": "//bazel/requirements:all.txt"},
	}

	got := detectLockfiles(r, cfg)
	if len(got) != 0 {
		t.Errorf("detectLockfiles() with only local deps = %v, want nil/empty", got)
	}
}

// ---------------------------------------------------------------------------
// detectScaRules
// ---------------------------------------------------------------------------

func TestDetectScaRules_ScaDisabled(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{"@pip//requests"})

	cfg := &semgrepConfig{
		scaEnabled: false,
		scaRules:   map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"},
	}

	got := detectScaRules(r, cfg)
	if got != nil {
		t.Errorf("detectScaRules() with scaEnabled=false = %v, want nil", got)
	}
}

func TestDetectScaRules_EmptyScaRulesMap(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	r.SetAttr("deps", []string{"@pip//requests"})

	cfg := &semgrepConfig{
		scaEnabled: true,
		scaRules:   map[string]string{},
	}

	got := detectScaRules(r, cfg)
	if len(got) != 0 {
		t.Errorf("detectScaRules() with empty scaRules map = %v, want nil/empty", got)
	}
}

func TestDetectScaRules_EmptyDeps(t *testing.T) {
	r := rule.NewRule("py_venv_binary", "test")
	// No deps attr set.

	cfg := &semgrepConfig{
		scaEnabled: true,
		scaRules:   map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"},
	}

	got := detectScaRules(r, cfg)
	if len(got) != 0 {
		t.Errorf("detectScaRules() with no deps = %v, want nil/empty", got)
	}
}

func TestDetectScaRules_TableDriven(t *testing.T) {
	tests := []struct {
		name       string
		deps       []string
		scaEnabled bool
		scaRules   map[string]string
		want       []string
	}{
		{
			name:       "pip dep detected",
			deps:       []string{"@pip//requests"},
			scaEnabled: true,
			scaRules:   map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"},
			want:       []string{"//bazel/semgrep/rules:sca_python_rules"},
		},
		{
			name:       "npm dep detected",
			deps:       []string{"@npm//react"},
			scaEnabled: true,
			scaRules:   map[string]string{"pnpm": "//bazel/semgrep/rules:sca_javascript_rules"},
			want:       []string{"//bazel/semgrep/rules:sca_javascript_rules"},
		},
		{
			name:       "go_deps dep detected",
			deps:       []string{"@go_deps//example.com/pkg"},
			scaEnabled: true,
			scaRules:   map[string]string{"gomod": "//bazel/semgrep/rules:sca_golang_rules"},
			want:       []string{"//bazel/semgrep/rules:sca_golang_rules"},
		},
		{
			name:       "no external deps",
			deps:       []string{":local_lib", "//other:target"},
			scaEnabled: true,
			scaRules:   map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"},
			want:       nil,
		},
		{
			name:       "sca disabled",
			deps:       []string{"@pip//requests"},
			scaEnabled: false,
			scaRules:   map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"},
			want:       nil,
		},
		{
			name:       "multiple ecosystems sorted",
			deps:       []string{"@pip//requests", "@go_deps//example.com/pkg"},
			scaEnabled: true,
			scaRules: map[string]string{
				"pip":   "//bazel/semgrep/rules:sca_python_rules",
				"gomod": "//bazel/semgrep/rules:sca_golang_rules",
			},
			// sorted: sca_golang_rules < sca_python_rules
			want: []string{
				"//bazel/semgrep/rules:sca_golang_rules",
				"//bazel/semgrep/rules:sca_python_rules",
			},
		},
		{
			name:       "all three ecosystems sorted",
			deps:       []string{"@pip//requests", "@npm//react", "@go_deps//example.com/pkg"},
			scaEnabled: true,
			scaRules: map[string]string{
				"pip":   "//bazel/semgrep/rules:sca_python_rules",
				"pnpm":  "//bazel/semgrep/rules:sca_javascript_rules",
				"gomod": "//bazel/semgrep/rules:sca_golang_rules",
			},
			// sorted lexicographically
			want: []string{
				"//bazel/semgrep/rules:sca_golang_rules",
				"//bazel/semgrep/rules:sca_javascript_rules",
				"//bazel/semgrep/rules:sca_python_rules",
			},
		},
		{
			name:       "ecosystem without sca rules config",
			deps:       []string{"@pip//requests"},
			scaEnabled: true,
			scaRules:   map[string]string{"gomod": "//bazel/semgrep/rules:sca_golang_rules"},
			want:       nil,
		},
		{
			name:       "duplicate ecosystem deps yield single rule",
			deps:       []string{"@pip//requests", "@pip//flask"},
			scaEnabled: true,
			scaRules:   map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"},
			want:       []string{"//bazel/semgrep/rules:sca_python_rules"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			r := rule.NewRule("py_venv_binary", "test")
			r.SetAttr("deps", tc.deps)

			cfg := &semgrepConfig{
				scaEnabled: tc.scaEnabled,
				scaRules:   tc.scaRules,
			}

			got := detectScaRules(r, cfg)
			if len(got) != len(tc.want) {
				t.Fatalf("detectScaRules() = %v (len %d), want %v (len %d)",
					got, len(got), tc.want, len(tc.want))
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Errorf("[%d] = %q, want %q", i, got[i], tc.want[i])
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// copyLockfiles
// ---------------------------------------------------------------------------

func TestCopyLockfiles_Nil(t *testing.T) {
	got := copyLockfiles(nil)
	if got != nil {
		t.Errorf("copyLockfiles(nil) = %v, want nil", got)
	}
}

func TestCopyLockfiles_PopulatedMap(t *testing.T) {
	src := map[string]string{
		"pip":   "//bazel/requirements:all.txt",
		"pnpm":  "//:pnpm-lock.yaml",
		"gomod": "//:go.sum",
	}

	dst := copyLockfiles(src)

	if len(dst) != len(src) {
		t.Fatalf("copyLockfiles() len = %d, want %d", len(dst), len(src))
	}
	for k, v := range src {
		if dst[k] != v {
			t.Errorf("copyLockfiles()[%q] = %q, want %q", k, dst[k], v)
		}
	}
}

func TestCopyLockfiles_IndependenceFromSource(t *testing.T) {
	src := map[string]string{"pip": "//bazel/requirements:all.txt"}
	dst := copyLockfiles(src)

	// Mutate the copy.
	dst["pip"] = "//changed:lockfile"
	dst["gomod"] = "//:go.sum"

	// Source must be unchanged.
	if src["pip"] != "//bazel/requirements:all.txt" {
		t.Errorf("source pip was mutated: got %q", src["pip"])
	}
	if _, ok := src["gomod"]; ok {
		t.Error("source should not have acquired gomod key from copy mutation")
	}
}

func TestCopyLockfiles_EmptyMap(t *testing.T) {
	src := map[string]string{}
	dst := copyLockfiles(src)

	if dst == nil {
		t.Error("copyLockfiles(empty map) should return non-nil empty map, got nil")
	}
	if len(dst) != 0 {
		t.Errorf("copyLockfiles(empty map) len = %d, want 0", len(dst))
	}
}

// ---------------------------------------------------------------------------
// copyScaRules
// ---------------------------------------------------------------------------

func TestCopyScaRules_Nil(t *testing.T) {
	got := copyScaRules(nil)
	if got != nil {
		t.Errorf("copyScaRules(nil) = %v, want nil", got)
	}
}

func TestCopyScaRules_PopulatedMap(t *testing.T) {
	src := map[string]string{
		"pip":   "//bazel/semgrep/rules:sca_python_rules",
		"pnpm":  "//bazel/semgrep/rules:sca_javascript_rules",
		"gomod": "//bazel/semgrep/rules:sca_golang_rules",
	}

	dst := copyScaRules(src)

	if len(dst) != len(src) {
		t.Fatalf("copyScaRules() len = %d, want %d", len(dst), len(src))
	}
	for k, v := range src {
		if dst[k] != v {
			t.Errorf("copyScaRules()[%q] = %q, want %q", k, dst[k], v)
		}
	}
}

func TestCopyScaRules_IndependenceFromSource(t *testing.T) {
	src := map[string]string{"pip": "//bazel/semgrep/rules:sca_python_rules"}
	dst := copyScaRules(src)

	// Mutate the copy.
	dst["pip"] = "//changed:rules"
	dst["gomod"] = "//bazel/semgrep/rules:sca_golang_rules"

	// Source must be unchanged.
	if src["pip"] != "//bazel/semgrep/rules:sca_python_rules" {
		t.Errorf("source pip was mutated: got %q", src["pip"])
	}
	if _, ok := src["gomod"]; ok {
		t.Error("source should not have acquired gomod key from copy mutation")
	}
}

func TestCopyScaRules_EmptyMap(t *testing.T) {
	src := map[string]string{}
	dst := copyScaRules(src)

	if dst == nil {
		t.Error("copyScaRules(empty map) should return non-nil empty map, got nil")
	}
	if len(dst) != 0 {
		t.Errorf("copyScaRules(empty map) len = %d, want 0", len(dst))
	}
}
