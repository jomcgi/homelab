package cmd

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/spf13/cobra"
)

const validStateMachineYAML = `apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
    initial: true
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`

const invalidYAML = `not: valid: yaml: [[[`

const missingInitialStateYAML = `apiVersion: controlflow.io/v1alpha1
kind: StateMachine
metadata:
  name: TestResource
  group: test.io
  version: v1alpha1
status:
  phaseField: phase
states:
  - name: Pending
  - name: Ready
    terminal: true
transitions:
  - from: Pending
    to: Ready
    action: MarkReady
`

func writeYAMLFile(t *testing.T, content string) string {
	t.Helper()
	f, err := os.CreateTemp(t.TempDir(), "*.sextant.yaml")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	if _, err := f.WriteString(content); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}
	if err := f.Close(); err != nil {
		t.Fatalf("failed to close temp file: %v", err)
	}
	return f.Name()
}

func resetValidateFlags() {
	validateOutputXState = false
	validateOutputPath = ""
}

func resetGenerateFlags() {
	generateOutputDir = "./pkg/statemachine"
	generatePackage = ""
	generateModule = ""
	generateAPIImportPath = ""
}

// ---- validate tests ----

func TestRunValidate_ValidFile(t *testing.T) {
	defer resetValidateFlags()

	filePath := writeYAMLFile(t, validStateMachineYAML)
	err := runValidate(&cobra.Command{}, []string{filePath})
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
}

func TestRunValidate_FileNotFound(t *testing.T) {
	defer resetValidateFlags()

	err := runValidate(&cobra.Command{}, []string{"/nonexistent/path/does-not-exist.sextant.yaml"})
	if err == nil {
		t.Fatal("expected error for non-existent file, got nil")
	}
}

func TestRunValidate_InvalidYAML(t *testing.T) {
	defer resetValidateFlags()

	filePath := writeYAMLFile(t, invalidYAML)
	err := runValidate(&cobra.Command{}, []string{filePath})
	if err == nil {
		t.Fatal("expected error for invalid YAML, got nil")
	}
}

func TestRunValidate_MissingInitialState(t *testing.T) {
	defer resetValidateFlags()

	filePath := writeYAMLFile(t, missingInitialStateYAML)
	err := runValidate(&cobra.Command{}, []string{filePath})
	if err == nil {
		t.Fatal("expected validation error for missing initial state, got nil")
	}
	if !strings.Contains(err.Error(), "initial") {
		t.Errorf("expected error to mention 'initial', got: %v", err)
	}
}

func TestRunValidate_WithXStateFlag_WritesToStdout(t *testing.T) {
	defer resetValidateFlags()

	validateOutputXState = true

	filePath := writeYAMLFile(t, validStateMachineYAML)

	// Capture stdout
	origStdout := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("failed to create pipe: %v", err)
	}
	os.Stdout = w

	runErr := runValidate(&cobra.Command{}, []string{filePath})

	w.Close()
	os.Stdout = origStdout

	if runErr != nil {
		t.Fatalf("expected no error, got: %v", runErr)
	}

	buf := make([]byte, 65536)
	n, _ := r.Read(buf)
	output := string(buf[:n])

	if !json.Valid([]byte(output)) {
		t.Errorf("expected valid JSON on stdout, got: %s", output)
	}
}

func TestRunValidate_WithXStateAndOutputFile(t *testing.T) {
	defer resetValidateFlags()

	validateOutputXState = true
	outFile := filepath.Join(t.TempDir(), "out.xstate.json")
	validateOutputPath = outFile

	filePath := writeYAMLFile(t, validStateMachineYAML)
	err := runValidate(&cobra.Command{}, []string{filePath})
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}

	content, err := os.ReadFile(outFile)
	if err != nil {
		t.Fatalf("expected output file to exist: %v", err)
	}
	if !json.Valid(content) {
		t.Errorf("expected valid JSON in output file, got: %s", content)
	}
}

func TestValidateCmd_RequiresExactlyOneArg(t *testing.T) {
	cmd := validateCmd

	if err := cmd.Args(cmd, []string{}); err == nil {
		t.Error("expected error with 0 args, got nil")
	}
	if err := cmd.Args(cmd, []string{"a", "b"}); err == nil {
		t.Error("expected error with 2 args, got nil")
	}
	if err := cmd.Args(cmd, []string{"a"}); err != nil {
		t.Errorf("expected no error with 1 arg, got: %v", err)
	}
}

// ---- generate tests ----

func TestRunGenerate_ValidFile(t *testing.T) {
	defer resetGenerateFlags()

	outDir := t.TempDir()
	generateOutputDir = outDir
	generatePackage = "testpkg"

	filePath := writeYAMLFile(t, validStateMachineYAML)
	err := runGenerate(&cobra.Command{}, []string{filePath})
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}

	entries, err := os.ReadDir(outDir)
	if err != nil {
		t.Fatalf("failed to read output dir: %v", err)
	}
	if len(entries) == 0 {
		t.Error("expected generated files in output directory, found none")
	}
}

func TestRunGenerate_FileNotFound(t *testing.T) {
	defer resetGenerateFlags()

	generateOutputDir = t.TempDir()
	generatePackage = "testpkg"

	err := runGenerate(&cobra.Command{}, []string{"/nonexistent/path/does-not-exist.sextant.yaml"})
	if err == nil {
		t.Fatal("expected error for non-existent file, got nil")
	}
}

func TestRunGenerate_InvalidYAML(t *testing.T) {
	defer resetGenerateFlags()

	generateOutputDir = t.TempDir()
	generatePackage = "testpkg"

	filePath := writeYAMLFile(t, invalidYAML)
	err := runGenerate(&cobra.Command{}, []string{filePath})
	if err == nil {
		t.Fatal("expected error for invalid YAML, got nil")
	}
}

func TestRunGenerate_CustomPackageName(t *testing.T) {
	defer resetGenerateFlags()

	outDir := t.TempDir()
	generateOutputDir = outDir
	generatePackage = "mysm"

	filePath := writeYAMLFile(t, validStateMachineYAML)
	err := runGenerate(&cobra.Command{}, []string{filePath})
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}

	entries, err := os.ReadDir(outDir)
	if err != nil {
		t.Fatalf("failed to read output dir: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("expected generated files, found none")
	}

	// Verify at least one generated file uses the custom package name
	found := false
	for _, e := range entries {
		content, err := os.ReadFile(filepath.Join(outDir, e.Name()))
		if err != nil {
			continue
		}
		if strings.Contains(string(content), "package mysm") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected at least one generated file to contain 'package mysm'")
	}
}

func TestRunGenerate_DefaultsPackageFromDirName(t *testing.T) {
	defer resetGenerateFlags()

	outDir := filepath.Join(t.TempDir(), "mypkg")
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		t.Fatalf("failed to create output dir: %v", err)
	}
	generateOutputDir = outDir
	generatePackage = "" // let it default from dir name

	filePath := writeYAMLFile(t, validStateMachineYAML)
	err := runGenerate(&cobra.Command{}, []string{filePath})
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}

	entries, err := os.ReadDir(outDir)
	if err != nil {
		t.Fatalf("failed to read output dir: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("expected generated files, found none")
	}

	found := false
	for _, e := range entries {
		content, err := os.ReadFile(filepath.Join(outDir, e.Name()))
		if err != nil {
			continue
		}
		if strings.Contains(string(content), "package mypkg") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected at least one generated file to contain 'package mypkg' (derived from dir name)")
	}
}

func TestRunGenerate_WithModuleAndAPIPath(t *testing.T) {
	defer resetGenerateFlags()

	outDir := t.TempDir()
	generateOutputDir = outDir
	generatePackage = "testpkg"
	generateModule = "github.com/example/operator"
	generateAPIImportPath = "github.com/example/operator/api/v1alpha1"

	filePath := writeYAMLFile(t, validStateMachineYAML)
	err := runGenerate(&cobra.Command{}, []string{filePath})
	if err != nil {
		t.Fatalf("expected no error with module and api flags, got: %v", err)
	}
}

func TestGenerateCmd_RequiresExactlyOneArg(t *testing.T) {
	cmd := generateCmd

	if err := cmd.Args(cmd, []string{}); err == nil {
		t.Error("expected error with 0 args, got nil")
	}
	if err := cmd.Args(cmd, []string{"a", "b"}); err == nil {
		t.Error("expected error with 2 args, got nil")
	}
	if err := cmd.Args(cmd, []string{"a"}); err != nil {
		t.Errorf("expected no error with 1 arg, got: %v", err)
	}
}
