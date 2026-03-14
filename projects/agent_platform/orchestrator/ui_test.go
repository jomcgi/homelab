package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// mkTempUIDir creates a temporary directory with a minimal UI layout:
// index.html plus a static asset (app.js). It is cleaned up automatically
// when the test ends.
func mkTempUIDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "index.html"), "<html>index</html>")
	writeFile(t, filepath.Join(dir, "app.js"), "console.log('app')")
	return dir
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("os.WriteFile(%q): %v", path, err)
	}
}

// overrideUIDir replaces the package-level uiDir for the duration of the
// test and restores the original value via t.Cleanup.
func overrideUIDir(t *testing.T, dir string) {
	t.Helper()
	orig := uiDir
	uiDir = dir
	t.Cleanup(func() { uiDir = orig })
}

// newUITestServer starts an httptest server with registerUI mounted.
// uiDir must be set (via overrideUIDir) before calling this.
func newUITestServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	registerUI(mux)
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// ---- getUIDir ---------------------------------------------------------------

func TestGetUIDir_DefaultsToOptUI(t *testing.T) {
	t.Setenv("UI_DIR", "") // ensure empty so the default branch is taken
	if got := getUIDir(); got != "/opt/ui" {
		t.Errorf("getUIDir() = %q, want %q", got, "/opt/ui")
	}
}

func TestGetUIDir_UsesEnvVar(t *testing.T) {
	t.Setenv("UI_DIR", "/custom/ui")
	if got := getUIDir(); got != "/custom/ui" {
		t.Errorf("getUIDir() = %q, want %q", got, "/custom/ui")
	}
}

// ---- registerUI -------------------------------------------------------------

func TestRegisterUI_RootPathServesIndex(t *testing.T) {
	overrideUIDir(t, mkTempUIDir(t))
	srv := newUITestServer(t)

	resp, err := http.Get(srv.URL + "/")
	if err != nil {
		t.Fatalf("GET /: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want %d", resp.StatusCode, http.StatusOK)
	}
	if got := string(body); got != "<html>index</html>" {
		t.Errorf("body = %q, want %q", got, "<html>index</html>")
	}
}

func TestRegisterUI_ServesExistingStaticAsset(t *testing.T) {
	overrideUIDir(t, mkTempUIDir(t))
	srv := newUITestServer(t)

	resp, err := http.Get(srv.URL + "/app.js")
	if err != nil {
		t.Fatalf("GET /app.js: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want %d", resp.StatusCode, http.StatusOK)
	}
	if got := string(body); got != "console.log('app')" {
		t.Errorf("body = %q, want %q", got, "console.log('app')")
	}
}

func TestRegisterUI_SPAFallbackForUnknownRoute(t *testing.T) {
	overrideUIDir(t, mkTempUIDir(t))
	srv := newUITestServer(t)

	// /some/spa/route does not exist on disk — should fall back to index.html.
	resp, err := http.Get(srv.URL + "/some/spa/route")
	if err != nil {
		t.Fatalf("GET /some/spa/route: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want %d", resp.StatusCode, http.StatusOK)
	}
	if got := string(body); got != "<html>index</html>" {
		t.Errorf("SPA fallback body = %q, want index.html content %q", got, "<html>index</html>")
	}
}

func TestRegisterUI_SPAFallbackForUnknownNestedRoute(t *testing.T) {
	overrideUIDir(t, mkTempUIDir(t))
	srv := newUITestServer(t)

	resp, err := http.Get(srv.URL + "/jobs/abc-123/details")
	if err != nil {
		t.Fatalf("GET /jobs/abc-123/details: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want %d", resp.StatusCode, http.StatusOK)
	}
	if got := string(body); got != "<html>index</html>" {
		t.Errorf("SPA fallback body = %q, want index.html content %q", got, "<html>index</html>")
	}
}
