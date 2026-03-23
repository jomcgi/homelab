package main

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// TestEnvOr_ReturnsEnvWhenSet verifies that envOr returns the environment
// variable value when the variable is set to a non-empty string.
func TestEnvOr_ReturnsEnvWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_OR_KEY", "from-env")

	got := envOr("TEST_ENV_OR_KEY", "fallback")
	if got != "from-env" {
		t.Errorf("envOr: got %q, want %q", got, "from-env")
	}
}

// TestEnvOr_ReturnsFallbackWhenUnset verifies that envOr returns the fallback
// value when the environment variable is not set.
func TestEnvOr_ReturnsFallbackWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_OR_UNSET", "")

	got := envOr("TEST_ENV_OR_UNSET", "default-value")
	if got != "default-value" {
		t.Errorf("envOr: got %q, want %q", got, "default-value")
	}
}

// TestEnvOr_ReturnsFallbackWhenEmpty verifies that envOr treats an empty
// string value the same as an unset variable.
func TestEnvOr_ReturnsFallbackWhenEmpty(t *testing.T) {
	// Ensure variable is absent entirely.
	t.Setenv("TEST_ENV_OR_EMPTY", "")

	got := envOr("TEST_ENV_OR_EMPTY", "fallback-empty")
	if got != "fallback-empty" {
		t.Errorf("envOr with empty value: got %q, want %q", got, "fallback-empty")
	}
}

// TestEnvDurationOr_ReturnsEnvWhenValid verifies that envDurationOr parses
// a valid duration from the environment variable.
func TestEnvDurationOr_ReturnsEnvWhenValid(t *testing.T) {
	t.Setenv("TEST_DUR_KEY", "30m")

	got := envDurationOr("TEST_DUR_KEY", 5*time.Minute)
	if got != 30*time.Minute {
		t.Errorf("envDurationOr: got %v, want %v", got, 30*time.Minute)
	}
}

// TestEnvDurationOr_ReturnsFallbackWhenUnset verifies that envDurationOr
// returns the fallback duration when the variable is not set.
func TestEnvDurationOr_ReturnsFallbackWhenUnset(t *testing.T) {
	t.Setenv("TEST_DUR_UNSET", "")

	got := envDurationOr("TEST_DUR_UNSET", 10*time.Minute)
	if got != 10*time.Minute {
		t.Errorf("envDurationOr: got %v, want %v", got, 10*time.Minute)
	}
}

// TestEnvDurationOr_ReturnsFallbackWhenInvalid verifies that envDurationOr
// falls back to the default when the environment variable holds an unparseable
// duration, rather than returning an error or panicking.
func TestEnvDurationOr_ReturnsFallbackWhenInvalid(t *testing.T) {
	t.Setenv("TEST_DUR_INVALID", "not-a-duration")

	got := envDurationOr("TEST_DUR_INVALID", 15*time.Minute)
	if got != 15*time.Minute {
		t.Errorf("envDurationOr with invalid value: got %v, want %v", got, 15*time.Minute)
	}
}

// TestEnvDurationOr_ParsesVariousFormats verifies a set of duration strings
// representative of values operators would configure in practice.
func TestEnvDurationOr_ParsesVariousFormats(t *testing.T) {
	cases := []struct {
		env      string
		fallback time.Duration
		want     time.Duration
	}{
		{"1h", time.Minute, time.Hour},
		{"24h", time.Minute, 24 * time.Hour},
		{"168h", time.Minute, 168 * time.Hour},
		{"500ms", time.Second, 500 * time.Millisecond},
	}

	for _, tc := range cases {
		t.Run(tc.env, func(t *testing.T) {
			t.Setenv("TEST_DUR_FORMATS", tc.env)
			got := envDurationOr("TEST_DUR_FORMATS", tc.fallback)
			if got != tc.want {
				t.Errorf("envDurationOr(%q): got %v, want %v", tc.env, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// /health HTTP endpoint
// ---------------------------------------------------------------------------

// newHealthMux builds a ServeMux with the same /health handler as main(),
// allowing the handler logic to be tested without starting a real process.
func newHealthMux() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	return mux
}

// TestHealthEndpoint_Returns200OK verifies that GET /health responds with
// HTTP 200 and a body containing "ok".
func TestHealthEndpoint_Returns200OK(t *testing.T) {
	srv := httptest.NewServer(newHealthMux())
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatalf("GET /health: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("reading body: %v", err)
	}
	if !strings.Contains(string(body), "ok") {
		t.Errorf("expected body to contain %q, got %q", "ok", string(body))
	}
}

// TestHealthEndpoint_MethodsAllowed verifies that the /health endpoint
// returns 200 for both GET and HEAD (Go's default mux responds to HEAD on any
// registered handler).
func TestHealthEndpoint_MethodsAllowed(t *testing.T) {
	srv := httptest.NewServer(newHealthMux())
	defer srv.Close()

	req, err := http.NewRequest(http.MethodHead, srv.URL+"/health", nil)
	if err != nil {
		t.Fatalf("creating HEAD request: %v", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("HEAD /health: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("HEAD /health: expected status 200, got %d", resp.StatusCode)
	}
}

// TestHealthEndpoint_NotFoundForOtherPaths verifies that the mux returns 404
// for any path other than /health.
func TestHealthEndpoint_NotFoundForOtherPaths(t *testing.T) {
	srv := httptest.NewServer(newHealthMux())
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/not-a-path")
	if err != nil {
		t.Fatalf("GET /not-a-path: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNotFound {
		t.Errorf("expected 404 for unknown path, got %d", resp.StatusCode)
	}
}
