package gazelle

import (
	"os"
	"path/filepath"
	"testing"
)

func TestParseWranglerJSONC_PlainJSON(t *testing.T) {
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "wrangler.jsonc")
	if err := os.WriteFile(path, []byte(`{"name": "my-project"}`), 0o644); err != nil {
		t.Fatalf("Failed to write file: %v", err)
	}

	cfg, err := parseWranglerJSONC(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.Name != "my-project" {
		t.Errorf("Name = %q, want %q", cfg.Name, "my-project")
	}
}

func TestParseWranglerJSONC_WithComments(t *testing.T) {
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "wrangler.jsonc")
	content := `// Cloudflare Pages configuration
{
  // Project name used for deployment
  "name": "commented-project"
}
`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("Failed to write file: %v", err)
	}

	cfg, err := parseWranglerJSONC(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.Name != "commented-project" {
		t.Errorf("Name = %q, want %q", cfg.Name, "commented-project")
	}
}

func TestParseWranglerJSONC_InvalidJSON(t *testing.T) {
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "wrangler.jsonc")
	if err := os.WriteFile(path, []byte(`{invalid json}`), 0o644); err != nil {
		t.Fatalf("Failed to write file: %v", err)
	}

	_, err := parseWranglerJSONC(path)
	if err == nil {
		t.Error("expected error for invalid JSON, got nil")
	}
}

func TestParseWranglerJSONC_EmptyName(t *testing.T) {
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "wrangler.jsonc")
	if err := os.WriteFile(path, []byte(`{}`), 0o644); err != nil {
		t.Fatalf("Failed to write file: %v", err)
	}

	cfg, err := parseWranglerJSONC(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.Name != "" {
		t.Errorf("Name = %q, want empty", cfg.Name)
	}
}

func TestParseWranglerJSONC_FileNotFound(t *testing.T) {
	_, err := parseWranglerJSONC("/nonexistent/path/wrangler.jsonc")
	if err == nil {
		t.Error("expected error for nonexistent file, got nil")
	}
}

func TestDeriveTargetName(t *testing.T) {
	tests := []struct {
		rel  string
		want string
	}{
		{"websites/trips.jomcgi.dev", "trips"},
		{"websites/jomcgi.dev", "jomcgi"},
		{"websites/hikes.jomcgi.dev", "hikes"},
		{"simple", "simple"},
		{"path/to/app.example.com", "app"},
	}

	for _, tc := range tests {
		t.Run(tc.rel, func(t *testing.T) {
			got := deriveTargetName(tc.rel)
			if got != tc.want {
				t.Errorf("deriveTargetName(%q) = %q, want %q", tc.rel, got, tc.want)
			}
		})
	}
}
