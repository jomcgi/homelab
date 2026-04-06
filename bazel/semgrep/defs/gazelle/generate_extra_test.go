package gazelle

import (
	"testing"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
)

// TestGenerateRules_LockfilesDetectedButScaRulesEmpty verifies that when
// lockfiles are detected (non-empty) but the scaRules config map is empty,
// the generated rule gets the lockfiles attr but NOT the sca_rules attr.
func TestGenerateRules_LockfilesDetectedButScaRulesEmpty(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:    true,
				scaEnabled: true,
				// scaRules is empty — no SCA rules configured
				scaRules:    map[string]string{},
				lockfiles:   map[string]string{"pip": "//bazel/requirements:all.txt"},
				targetKinds: map[string]string{"py_venv_binary": ""},
				languages:   []string{"py"},
			},
		},
	}

	binary := newPyBinaryWithDeps("server", "server.py", []string{"@pip//requests"})
	buildFile := buildFileWithRules(binary)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"server.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	if len(result.Gen) < 1 {
		t.Fatalf("expected at least 1 generated rule, got 0")
	}

	targetRule := result.Gen[0]
	if targetRule.Kind() != "semgrep_target_test" {
		t.Fatalf("rule[0] kind = %q, want semgrep_target_test", targetRule.Kind())
	}

	// lockfiles should be set (pip dep was detected)
	lockfiles := targetRule.AttrStrings("lockfiles")
	if len(lockfiles) != 1 || lockfiles[0] != "//bazel/requirements:all.txt" {
		t.Errorf("lockfiles = %v, want [//bazel/requirements:all.txt]", lockfiles)
	}

	// sca_rules should NOT be set (empty scaRules config)
	scaRules := targetRule.AttrStrings("sca_rules")
	if len(scaRules) != 0 {
		t.Errorf("sca_rules should be empty when scaRules config is empty, got %v", scaRules)
	}
}

// TestGenerateRules_SCAEnabledEmptyLockfilesConfig verifies that when SCA is
// enabled but the lockfiles map is empty, no lockfiles or sca_rules attrs
// are added even if the binary has external deps.
func TestGenerateRules_SCAEnabledEmptyLockfilesConfig(t *testing.T) {
	c := &config.Config{
		Exts: map[string]interface{}{
			semgrepConfigKey: &semgrepConfig{
				enabled:     true,
				scaEnabled:  true,
				scaRules:    copyScaRules(defaultScaRules),
				lockfiles:   map[string]string{}, // no lockfiles configured
				targetKinds: map[string]string{"py_venv_binary": ""},
				languages:   []string{"py"},
			},
		},
	}

	binary := newPyBinaryWithDeps("server", "server.py", []string{"@pip//requests"})
	buildFile := buildFileWithRules(binary)

	args := language.GenerateArgs{
		Config:       c,
		Dir:          "/tmp/test",
		Rel:          "services/myapp",
		RegularFiles: []string{"server.py"},
		File:         buildFile,
	}

	result := generateRules(args)

	if len(result.Gen) < 1 {
		t.Fatalf("expected at least 1 generated rule, got 0")
	}

	targetRule := result.Gen[0]

	// Neither lockfiles nor sca_rules should be set
	lockfiles := targetRule.AttrStrings("lockfiles")
	if len(lockfiles) != 0 {
		t.Errorf("lockfiles should be empty when lockfiles config is empty, got %v", lockfiles)
	}

	scaRules := targetRule.AttrStrings("sca_rules")
	if len(scaRules) != 0 {
		t.Errorf("sca_rules should be empty when lockfiles config is empty, got %v", scaRules)
	}
}
