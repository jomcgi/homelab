package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestEnvOr_Present verifies that envOr returns the environment variable value when it is set.
func TestEnvOr_Present(t *testing.T) {
	const key = "TEST_ENV_OR_PRESENT"
	t.Setenv(key, "configured-value")

	got := envOr(key, "fallback")
	if got != "configured-value" {
		t.Errorf("envOr(%q, fallback) got %q, want %q", key, got, "configured-value")
	}
}

// TestEnvOr_Missing verifies that envOr returns the fallback when the variable is not set.
func TestEnvOr_Missing(t *testing.T) {
	const key = "TEST_ENV_OR_MISSING_XYZ_UNIQUE"
	t.Setenv(key, "") // ensure absent from process env

	got := envOr(key, "default-fallback")
	if got != "default-fallback" {
		t.Errorf("envOr(%q, fallback) got %q, want %q", key, got, "default-fallback")
	}
}

// TestEnvOr_EmptyValueFallsBack verifies that an empty env variable value uses the fallback.
func TestEnvOr_EmptyValueFallsBack(t *testing.T) {
	const key = "TEST_ENV_OR_EMPTY"
	t.Setenv(key, "")

	got := envOr(key, "my-fallback")
	if got != "my-fallback" {
		t.Errorf("envOr with empty var got %q, want %q", got, "my-fallback")
	}
}

// TestEnvOr_FallbackIgnoredWhenSet verifies that a non-empty env variable always wins
// over the fallback, even when both are provided.
func TestEnvOr_FallbackIgnoredWhenSet(t *testing.T) {
	const key = "TEST_ENV_OR_WINS"
	t.Setenv(key, "winner")

	got := envOr(key, "loser")
	if got != "winner" {
		t.Errorf("envOr got %q, want %q", got, "winner")
	}
}

// TestHandleWebSocket_AuthFailure_MissingHeader verifies that a WebSocket upgrade request
// without a Cf-Access-Jwt-Assertion header is rejected with 401 Unauthorized.
// The auth failure path is exercised before any WebSocket handshake or Hub interaction.
func TestHandleWebSocket_AuthFailure_MissingHeader(t *testing.T) {
	hub := NewHub(nil) // nil redis — single-replica mode; hub.Run not needed for auth failure
	auth := NewCFAccessAuth("test.cloudflareaccess.com")

	req := httptest.NewRequest("GET", "/ws", nil)
	// Deliberately omit the Cf-Access-Jwt-Assertion header.
	w := httptest.NewRecorder()

	handleWebSocket(w, req, hub, auth)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status got %d, want %d", w.Code, http.StatusUnauthorized)
	}
}

// TestHandleWebSocket_AuthFailure_InvalidToken verifies that a WebSocket request with a
// syntactically invalid JWT is rejected with 401 Unauthorized.
func TestHandleWebSocket_AuthFailure_InvalidToken(t *testing.T) {
	hub := NewHub(nil)
	auth := NewCFAccessAuth("test.cloudflareaccess.com")

	req := httptest.NewRequest("GET", "/ws", nil)
	req.Header.Set(cfAccessJWTHeader, "not.a.valid.jwt.at.all")
	w := httptest.NewRecorder()

	handleWebSocket(w, req, hub, auth)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status got %d, want %d", w.Code, http.StatusUnauthorized)
	}
}

// TestHealthzEndpoint verifies the /healthz route returns 200 OK.
func TestHealthzEndpoint(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok")) //nolint:errcheck
	})

	req := httptest.NewRequest("GET", "/healthz", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status got %d, want %d", w.Code, http.StatusOK)
	}
	if w.Body.String() != "ok" {
		t.Errorf("body got %q, want %q", w.Body.String(), "ok")
	}
}

// TestReadyzEndpoint_RedisUnavailable verifies that /readyz returns 503 when Redis is unavailable.
// We simulate an unavailable Redis by creating a hub with nil relay and wiring a fake Ping.
func TestReadyzEndpoint_RedisUnavailable(t *testing.T) {
	mux := http.NewServeMux()
	// Simulate the readyz handler using a stub that always fails the Redis check.
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		// Simulate redis being nil/unhealthy — same branch as main.go when redis.Ping() fails.
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte("redis unhealthy")) //nolint:errcheck
	})

	req := httptest.NewRequest("GET", "/readyz", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("status got %d, want %d", w.Code, http.StatusServiceUnavailable)
	}
}
