/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package utils

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// --- GetNonEmptyLines ---

// TestGetNonEmptyLines verifies that GetNonEmptyLines correctly splits output
// into non-empty lines, handling edge cases such as empty input, blank lines,
// and trailing newlines.
func TestGetNonEmptyLines(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    []string
		wantNil bool
	}{
		{
			name:    "empty string returns nil",
			input:   "",
			want:    nil,
			wantNil: true,
		},
		{
			name:  "single line without newline",
			input: "hello",
			want:  []string{"hello"},
		},
		{
			name:  "single line with trailing newline",
			input: "hello\n",
			want:  []string{"hello"},
		},
		{
			name:  "multiple lines",
			input: "line1\nline2\nline3",
			want:  []string{"line1", "line2", "line3"},
		},
		{
			name:  "multiple lines with trailing newline",
			input: "line1\nline2\nline3\n",
			want:  []string{"line1", "line2", "line3"},
		},
		{
			name:  "lines with blank lines in between",
			input: "line1\n\nline2\n\nline3",
			want:  []string{"line1", "line2", "line3"},
		},
		{
			name:    "only blank lines",
			input:   "\n\n\n",
			want:    nil,
			wantNil: true,
		},
		{
			name:  "leading blank line",
			input: "\nline1\nline2",
			want:  []string{"line1", "line2"},
		},
		{
			name:  "trailing blank lines",
			input: "line1\nline2\n\n",
			want:  []string{"line1", "line2"},
		},
		{
			name:  "single blank line between content",
			input: "NAME\n\nprometheus.monitoring.coreos.com\nprometheusrules.monitoring.coreos.com\n",
			want:  []string{"NAME", "prometheus.monitoring.coreos.com", "prometheusrules.monitoring.coreos.com"},
		},
		{
			name:  "line with only whitespace is kept (not empty)",
			input: "line1\n   \nline2",
			want:  []string{"line1", "   ", "line2"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := GetNonEmptyLines(tt.input)
			if tt.wantNil {
				if got != nil {
					t.Errorf("GetNonEmptyLines(%q) = %v, want nil", tt.input, got)
				}
				return
			}
			if len(got) != len(tt.want) {
				t.Errorf("GetNonEmptyLines(%q) returned %d lines, want %d: got=%v", tt.input, len(got), len(tt.want), got)
				return
			}
			for i, line := range got {
				if line != tt.want[i] {
					t.Errorf("GetNonEmptyLines(%q)[%d] = %q, want %q", tt.input, i, line, tt.want[i])
				}
			}
		})
	}
}

// TestGetNonEmptyLinesPreservesContent verifies that lines containing special
// characters are preserved as-is.
func TestGetNonEmptyLinesPreservesContent(t *testing.T) {
	input := "certificates.cert-manager.io\nissuers.cert-manager.io\nclusterissuers.cert-manager.io\n"
	got := GetNonEmptyLines(input)

	expected := []string{
		"certificates.cert-manager.io",
		"issuers.cert-manager.io",
		"clusterissuers.cert-manager.io",
	}

	if len(got) != len(expected) {
		t.Fatalf("expected %d lines, got %d: %v", len(expected), len(got), got)
	}
	for i, want := range expected {
		if got[i] != want {
			t.Errorf("line[%d]: got %q, want %q", i, got[i], want)
		}
	}
}

// --- GetProjectDir ---

// TestGetProjectDir verifies that GetProjectDir returns a non-empty path
// without any /test/e2e suffix.
func TestGetProjectDir(t *testing.T) {
	dir, err := GetProjectDir()
	if err != nil {
		t.Fatalf("GetProjectDir() error = %v", err)
	}
	if dir == "" {
		t.Error("GetProjectDir() returned empty string")
	}
	if strings.Contains(dir, "/test/e2e") {
		t.Errorf("GetProjectDir() = %q, must not contain '/test/e2e'", dir)
	}
}

// TestGetProjectDirMatchesGetwd verifies that when the working directory does
// NOT contain /test/e2e, GetProjectDir returns the same path as os.Getwd.
func TestGetProjectDirMatchesGetwd(t *testing.T) {
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("os.Getwd() error = %v", err)
	}
	if strings.Contains(cwd, "/test/e2e") {
		t.Skip("working directory contains /test/e2e; this test requires a path without that suffix")
	}

	dir, err := GetProjectDir()
	if err != nil {
		t.Fatalf("GetProjectDir() error = %v", err)
	}
	if dir != cwd {
		t.Errorf("GetProjectDir() = %q, want %q (same as os.Getwd)", dir, cwd)
	}
}

// TestGetProjectDirStripsE2ESuffix verifies the core behaviour: when the
// working directory contains /test/e2e, that suffix is removed.
// This is tested by temporarily changing the working directory.
func TestGetProjectDirStripsE2ESuffix(t *testing.T) {
	// Save original cwd and restore after test
	origDir, err := os.Getwd()
	if err != nil {
		t.Fatalf("os.Getwd() error = %v", err)
	}
	defer func() {
		if err := os.Chdir(origDir); err != nil {
			t.Logf("failed to restore working directory: %v", err)
		}
	}()

	// Create a temp directory that mimics .../test/e2e
	tmpBase := t.TempDir()
	e2eDir := filepath.Join(tmpBase, "test", "e2e")
	if err := os.MkdirAll(e2eDir, 0o755); err != nil {
		t.Fatalf("MkdirAll error = %v", err)
	}
	if err := os.Chdir(e2eDir); err != nil {
		t.Fatalf("Chdir error = %v", err)
	}

	dir, err := GetProjectDir()
	if err != nil {
		t.Fatalf("GetProjectDir() error = %v", err)
	}
	if strings.Contains(dir, "/test/e2e") {
		t.Errorf("GetProjectDir() = %q, should have stripped '/test/e2e'", dir)
	}
	// GetProjectDir strips /test/e2e via strings.ReplaceAll, so the result
	// should equal tmpBase (the part of the path before /test/e2e).
	if dir != tmpBase {
		t.Errorf("GetProjectDir() = %q, want %q", dir, tmpBase)
	}
}

// --- UncommentCode ---

// TestUncommentCode verifies that UncommentCode removes the given prefix from
// each line of the matched target block.
func TestUncommentCode(t *testing.T) {
	tests := []struct {
		name        string
		fileContent string
		target      string
		prefix      string
		wantContent string
		wantErr     bool
	}{
		{
			name: "single line prefix removal",
			fileContent: `package main

// uncomment_me
`,
			target:      "// uncomment_me",
			prefix:      "// ",
			wantContent: "package main\n\nuncomment_me\n",
		},
		{
			name: "multi-line prefix removal",
			fileContent: `package main

// import (
// 	"fmt"
// )
`,
			target: `// import (
// 	"fmt"
// )`,
			prefix: "// ",
			wantContent: `package main

import (
	"fmt"
)
`,
		},
		{
			name: "prefix not present on lines uses TrimPrefix (no-op)",
			fileContent: `before
TARGET_LINE
after
`,
			target:      "TARGET_LINE",
			prefix:      "// ",
			wantContent: "before\nTARGET_LINE\nafter\n",
		},
		{
			name: "target at beginning of file",
			fileContent: `// firstline
rest of file
`,
			target:      "// firstline",
			prefix:      "// ",
			wantContent: "firstline\nrest of file\n",
		},
		{
			name: "target at end of file (no trailing newline in target)",
			fileContent: `preamble
// lastline`,
			target:      "// lastline",
			prefix:      "// ",
			wantContent: "preamble\nlastline",
		},
		{
			name:        "target not found returns error",
			fileContent: "package main\n",
			target:      "// does_not_exist",
			prefix:      "// ",
			wantErr:     true,
		},
		{
			name: "empty prefix removes nothing",
			fileContent: `package main

// keep_comment
`,
			target:      "// keep_comment",
			prefix:      "",
			wantContent: "package main\n\n// keep_comment\n",
		},
		{
			name: "hash prefix removal",
			fileContent: `# section_start
# line_one
# line_two
`,
			target: `# line_one
# line_two`,
			prefix:      "# ",
			wantContent: "# section_start\nline_one\nline_two\n",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Write the initial content to a temp file
			f, err := os.CreateTemp(t.TempDir(), "uncomment-test-*.go")
			if err != nil {
				t.Fatalf("CreateTemp error = %v", err)
			}
			if _, err := f.WriteString(tt.fileContent); err != nil {
				f.Close()
				t.Fatalf("WriteString error = %v", err)
			}
			f.Close()

			err = UncommentCode(f.Name(), tt.target, tt.prefix)
			if (err != nil) != tt.wantErr {
				t.Errorf("UncommentCode() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr {
				return
			}

			got, err := os.ReadFile(f.Name())
			if err != nil {
				t.Fatalf("ReadFile error = %v", err)
			}
			if string(got) != tt.wantContent {
				t.Errorf("file content mismatch:\n  want: %q\n  got:  %q", tt.wantContent, string(got))
			}
		})
	}
}

// TestUncommentCodeTargetNotFound verifies the error message when the target
// string is not present in the file.
func TestUncommentCodeTargetNotFound(t *testing.T) {
	f, err := os.CreateTemp(t.TempDir(), "notfound-*.go")
	if err != nil {
		t.Fatalf("CreateTemp error = %v", err)
	}
	content := "package main\n\nfunc main() {}\n"
	if _, err := f.WriteString(content); err != nil {
		f.Close()
		t.Fatalf("WriteString error = %v", err)
	}
	f.Close()

	err = UncommentCode(f.Name(), "// missing_target", "// ")
	if err == nil {
		t.Fatal("expected error when target not found, got nil")
	}
	if !strings.Contains(err.Error(), "unable to find the code") {
		t.Errorf("error message %q should mention 'unable to find the code'", err.Error())
	}
}

// TestUncommentCodeFileNotFound verifies the error when the file does not
// exist.
func TestUncommentCodeFileNotFound(t *testing.T) {
	err := UncommentCode("/nonexistent/path/file.go", "target", "// ")
	if err == nil {
		t.Fatal("expected error for nonexistent file, got nil")
	}
	if !strings.Contains(err.Error(), "failed to read file") {
		t.Errorf("error message %q should mention 'failed to read file'", err.Error())
	}
}

// TestUncommentCodePreservesContentOutsideTarget verifies that content before
// and after the target block is not modified.
func TestUncommentCodePreservesContentOutsideTarget(t *testing.T) {
	fileContent := `package main

import "fmt"

// func hello() {
// 	fmt.Println("hello")
// }

func main() {
	fmt.Println("main")
}
`
	target := `// func hello() {
// 	fmt.Println("hello")
// }`
	prefix := "// "
	wantContent := `package main

import "fmt"

func hello() {
	fmt.Println("hello")
}

func main() {
	fmt.Println("main")
}
`

	f, err := os.CreateTemp(t.TempDir(), "preserve-test-*.go")
	if err != nil {
		t.Fatalf("CreateTemp error = %v", err)
	}
	if _, err := f.WriteString(fileContent); err != nil {
		f.Close()
		t.Fatalf("WriteString error = %v", err)
	}
	f.Close()

	if err := UncommentCode(f.Name(), target, prefix); err != nil {
		t.Fatalf("UncommentCode() error = %v", err)
	}

	got, err := os.ReadFile(f.Name())
	if err != nil {
		t.Fatalf("ReadFile error = %v", err)
	}
	if string(got) != wantContent {
		t.Errorf("content mismatch:\n  want: %q\n  got:  %q", wantContent, string(got))
	}
}
