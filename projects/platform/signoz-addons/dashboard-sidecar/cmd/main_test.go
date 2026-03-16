package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/fake"
)

// newTestLogger returns a logger that discards all output, keeping test output clean.
func newTestLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// newTestSidecar creates a Sidecar with a fake Kubernetes client and the given SigNoz URL.
func newTestSidecar(t *testing.T, signozURL string) *Sidecar {
	t.Helper()
	return &Sidecar{
		config: Config{
			SignozURL:         signozURL,
			Namespace:         "default",
			StateNamespace:    "signoz",
			MetricsAddr:       ":0",
			SignozAPIKey:      "test-api-key",
			ReconcileInterval: time.Minute,
		},
		clientset:    fake.NewClientset(),
		httpClient:   &http.Client{Timeout: 5 * time.Second},
		logger:       newTestLogger(),
		state:        make(StateStore),
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}
}

// newSidecarWithServer creates a Sidecar wired to a test HTTP server.
func newSidecarWithServer(t *testing.T, handler http.Handler) (*Sidecar, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	s := newTestSidecar(t, srv.URL)
	return s, srv
}

// newSidecarForExtract creates a minimal Sidecar for extract-only tests.
func newSidecarForExtract() *Sidecar {
	return &Sidecar{
		config:       Config{},
		clientset:    fake.NewClientset(),
		httpClient:   &http.Client{},
		logger:       newTestLogger(),
		state:        make(StateStore),
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}
}

// ============================================================================
// Pure function tests
// ============================================================================

func TestHashContent_Length(t *testing.T) {
	tests := []struct {
		name  string
		input []byte
	}{
		{"empty", []byte{}},
		{"hello", []byte("hello")},
		{"json", []byte(`{"key":"value"}`)},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			h := hashContent(tc.input)
			// SHA-256 produces 32 bytes = 64 hex chars
			if len(h) != 64 {
				t.Errorf("hashContent(%q) length = %d, want 64", tc.input, len(h))
			}
		})
	}
}

func TestHashContent_Deterministic(t *testing.T) {
	data := []byte(`{"title":"My Dashboard"}`)
	h1 := hashContent(data)
	h2 := hashContent(data)
	if h1 != h2 {
		t.Errorf("hashContent is not deterministic: %q != %q", h1, h2)
	}
}

func TestHashContent_Distinct(t *testing.T) {
	h1 := hashContent([]byte("aaa"))
	h2 := hashContent([]byte("bbb"))
	if h1 == h2 {
		t.Error("different inputs should produce different hashes")
	}
}

func TestComputeConfigHash_Deterministic(t *testing.T) {
	content := []byte(`{"title":"Test"}`)
	annotations := map[string]string{
		dashboardNameKey: "My Dashboard",
		dashboardTagsKey: "prod,infra",
	}
	h1 := computeConfigHash(content, annotations)
	h2 := computeConfigHash(content, annotations)
	if h1 != h2 {
		t.Errorf("computeConfigHash is not deterministic: %q != %q", h1, h2)
	}
}

func TestComputeConfigHash_DifferentContent(t *testing.T) {
	annotations := map[string]string{}
	h1 := computeConfigHash([]byte(`{"a":1}`), annotations)
	h2 := computeConfigHash([]byte(`{"a":2}`), annotations)
	if h1 == h2 {
		t.Error("different content should produce different hashes")
	}
}

func TestComputeConfigHash_DifferentAnnotations(t *testing.T) {
	content := []byte(`{"title":"Test"}`)
	h1 := computeConfigHash(content, map[string]string{dashboardNameKey: "Name A"})
	h2 := computeConfigHash(content, map[string]string{dashboardNameKey: "Name B"})
	if h1 == h2 {
		t.Error("different annotations should produce different hashes")
	}
}

func TestComputeConfigHash_NilAnnotations(t *testing.T) {
	// Should not panic on nil annotations map
	h := computeConfigHash([]byte(`{}`), nil)
	if len(h) != 64 {
		t.Errorf("expected 64-char hex hash, got %d chars", len(h))
	}
}

func TestMergeTags_Empty(t *testing.T) {
	result := mergeTags(nil, "")
	if len(result) != 1 {
		t.Fatalf("expected 1 tag (iac-managed), got %d: %v", len(result), result)
	}
	if result[0] != defaultManagedTag {
		t.Errorf("expected tag %q, got %q", defaultManagedTag, result[0])
	}
}

func TestMergeTags_ExistingTagsPreserved(t *testing.T) {
	existing := []interface{}{"my-team", "production"}
	result := mergeTags(existing, "")
	// Should have: my-team, production, iac-managed
	if len(result) != 3 {
		t.Fatalf("expected 3 tags, got %d: %v", len(result), result)
	}
	tagSet := make(map[string]bool)
	for _, tag := range result {
		tagSet[tag] = true
	}
	if !tagSet["my-team"] {
		t.Error("expected tag 'my-team'")
	}
	if !tagSet["production"] {
		t.Error("expected tag 'production'")
	}
	if !tagSet[defaultManagedTag] {
		t.Errorf("expected tag %q", defaultManagedTag)
	}
}

func TestMergeTags_AnnotationTags(t *testing.T) {
	result := mergeTags(nil, "team-a, infra , prod")
	tagSet := make(map[string]bool)
	for _, tag := range result {
		tagSet[tag] = true
	}
	if !tagSet["team-a"] {
		t.Error("expected tag 'team-a'")
	}
	if !tagSet["infra"] {
		t.Error("expected tag 'infra' (trimmed)")
	}
	if !tagSet["prod"] {
		t.Error("expected tag 'prod'")
	}
	if !tagSet[defaultManagedTag] {
		t.Errorf("expected tag %q", defaultManagedTag)
	}
}

func TestMergeTags_NoDuplicates(t *testing.T) {
	existing := []interface{}{defaultManagedTag, "prod"}
	result := mergeTags(existing, "prod,"+defaultManagedTag)
	tagSet := make(map[string]int)
	for _, tag := range result {
		tagSet[tag]++
	}
	for tag, count := range tagSet {
		if count > 1 {
			t.Errorf("tag %q appears %d times, want 1", tag, count)
		}
	}
}

func TestMergeTags_EmptyAnnotationEntries(t *testing.T) {
	// Comma-separated with empty parts (e.g. trailing comma)
	result := mergeTags(nil, "valid,,  ,")
	tagSet := make(map[string]bool)
	for _, tag := range result {
		tagSet[tag] = true
		if tag == "" {
			t.Error("empty tag should not be in result")
		}
	}
	if !tagSet["valid"] {
		t.Error("expected tag 'valid'")
	}
}

func TestMergeTags_NonStringExistingTagIgnored(t *testing.T) {
	// Non-string values in existing tags should be ignored
	existing := []interface{}{42, "real-tag", nil, true}
	result := mergeTags(existing, "")
	tagSet := make(map[string]bool)
	for _, tag := range result {
		tagSet[tag] = true
	}
	if !tagSet["real-tag"] {
		t.Error("expected tag 'real-tag'")
	}
	if !tagSet[defaultManagedTag] {
		t.Errorf("expected tag %q", defaultManagedTag)
	}
}

func TestGetEnv_Present(t *testing.T) {
	t.Setenv("TEST_GET_ENV_KEY", "hello")
	if got := getEnv("TEST_GET_ENV_KEY", "default"); got != "hello" {
		t.Errorf("getEnv = %q, want %q", got, "hello")
	}
}

func TestGetEnv_Absent(t *testing.T) {
	os.Unsetenv("TEST_GET_ENV_ABSENT")
	if got := getEnv("TEST_GET_ENV_ABSENT", "fallback"); got != "fallback" {
		t.Errorf("getEnv = %q, want %q", got, "fallback")
	}
}

func TestGetEnv_Empty(t *testing.T) {
	t.Setenv("TEST_GET_ENV_EMPTY", "")
	// Empty string should return fallback (mirrors production behaviour)
	if got := getEnv("TEST_GET_ENV_EMPTY", "fallback"); got != "fallback" {
		t.Errorf("getEnv with empty env = %q, want %q", got, "fallback")
	}
}

func TestGetDurationEnv_ValidDuration(t *testing.T) {
	t.Setenv("TEST_DURATION_KEY", "2m30s")
	got := getDurationEnv("TEST_DURATION_KEY", time.Minute)
	want := 2*time.Minute + 30*time.Second
	if got != want {
		t.Errorf("getDurationEnv = %v, want %v", got, want)
	}
}

func TestGetDurationEnv_InvalidDuration(t *testing.T) {
	t.Setenv("TEST_DURATION_INVALID", "not-a-duration")
	got := getDurationEnv("TEST_DURATION_INVALID", 5*time.Minute)
	if got != 5*time.Minute {
		t.Errorf("getDurationEnv with invalid = %v, want %v", got, 5*time.Minute)
	}
}

func TestGetDurationEnv_Absent(t *testing.T) {
	os.Unsetenv("TEST_DURATION_ABSENT")
	got := getDurationEnv("TEST_DURATION_ABSENT", 10*time.Second)
	if got != 10*time.Second {
		t.Errorf("getDurationEnv absent = %v, want %v", got, 10*time.Second)
	}
}

// ============================================================================
// extractDashboardJSON tests
// ============================================================================

func TestExtractDashboardJSON_DashboardJsonKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"dashboard.json": `{"title":"test"}`,
		},
	}
	got, err := s.extractDashboardJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"title":"test"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractDashboardJSON_AnyJsonKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"my-dashboard.json": `{"title":"any"}`,
		},
	}
	got, err := s.extractDashboardJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"title":"any"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractDashboardJSON_SingleKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"content": `{"title":"single"}`,
		},
	}
	got, err := s.extractDashboardJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"title":"single"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractDashboardJSON_NoValidKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"key1": "val1",
			"key2": "val2",
		},
	}
	_, err := s.extractDashboardJSON(cm)
	if err == nil {
		t.Error("expected error for multiple non-json keys, got nil")
	}
}

func TestExtractDashboardJSON_EmptyData(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{},
	}
	_, err := s.extractDashboardJSON(cm)
	if err == nil {
		t.Error("expected error for empty ConfigMap data, got nil")
	}
}

func TestExtractDashboardJSON_PrefersDashboardJsonOverOtherJson(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"dashboard.json": `{"title":"preferred"}`,
			"other.json":     `{"title":"not-this-one"}`,
		},
	}
	got, err := s.extractDashboardJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"title":"preferred"}` {
		t.Errorf("expected dashboard.json content, got: %q", got)
	}
}

// ============================================================================
// extractAlertJSON tests
// ============================================================================

func TestExtractAlertJSON_AlertJsonKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"alert.json": `{"alert":"my-alert"}`,
		},
	}
	got, err := s.extractAlertJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"alert":"my-alert"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractAlertJSON_AnyJsonKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"my-alert.json": `{"alert":"fallback"}`,
		},
	}
	got, err := s.extractAlertJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"alert":"fallback"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractAlertJSON_SingleKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"content": `{"alert":"single"}`,
		},
	}
	got, err := s.extractAlertJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"alert":"single"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractAlertJSON_NoValidKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"key1": "val1",
			"key2": "val2",
		},
	}
	_, err := s.extractAlertJSON(cm)
	if err == nil {
		t.Error("expected error for multiple non-json keys, got nil")
	}
}

// ============================================================================
// extractChannelJSON tests
// ============================================================================

func TestExtractChannelJSON_ChannelJsonKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"channel.json": `{"name":"slack"}`,
		},
	}
	got, err := s.extractChannelJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"name":"slack"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractChannelJSON_AnyJsonKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"my-channel.json": `{"name":"pagerduty"}`,
		},
	}
	got, err := s.extractChannelJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"name":"pagerduty"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractChannelJSON_SingleKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"data": `{"name":"single"}`,
		},
	}
	got, err := s.extractChannelJSON(cm)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got) != `{"name":"single"}` {
		t.Errorf("unexpected data: %q", got)
	}
}

func TestExtractChannelJSON_NoValidKey(t *testing.T) {
	s := newSidecarForExtract()
	cm := &corev1.ConfigMap{
		Data: map[string]string{
			"key1": "v1",
			"key2": "v2",
		},
	}
	_, err := s.extractChannelJSON(cm)
	if err == nil {
		t.Error("expected error, got nil")
	}
}

// ============================================================================
// setHeaders tests
// ============================================================================

func TestSetHeaders_WithAPIKey(t *testing.T) {
	s := &Sidecar{
		config: Config{SignozAPIKey: "secret-key"},
	}
	req, _ := http.NewRequest(http.MethodGet, "http://example.com", nil)
	s.setHeaders(req)

	if ct := req.Header.Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}
	if key := req.Header.Get("SIGNOZ-API-KEY"); key != "secret-key" {
		t.Errorf("SIGNOZ-API-KEY = %q, want %q", key, "secret-key")
	}
}

func TestSetHeaders_WithoutAPIKey(t *testing.T) {
	s := &Sidecar{
		config: Config{SignozAPIKey: ""},
	}
	req, _ := http.NewRequest(http.MethodGet, "http://example.com", nil)
	s.setHeaders(req)

	if ct := req.Header.Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}
	if key := req.Header.Get("SIGNOZ-API-KEY"); key != "" {
		t.Errorf("expected no SIGNOZ-API-KEY header, got %q", key)
	}
}

// ============================================================================
// SigNoz API call tests — using httptest.Server
// ============================================================================

func TestCreateDashboard_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.Header.Get("SIGNOZ-API-KEY") != "test-api-key" {
			t.Errorf("missing or wrong API key header")
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"uuid":"dashboard-uuid-123","data":{}}}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	uuid, err := s.createDashboard(context.Background(), map[string]interface{}{"title": "Test"})
	if err != nil {
		t.Fatalf("createDashboard failed: %v", err)
	}
	if uuid != "dashboard-uuid-123" {
		t.Errorf("uuid = %q, want %q", uuid, "dashboard-uuid-123")
	}
}

func TestCreateDashboard_HTTPError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	_, err := s.createDashboard(context.Background(), map[string]interface{}{"title": "Test"})
	if err == nil {
		t.Fatal("expected error for 500 response, got nil")
	}
}

func TestCreateDashboard_APIErrorStatus(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"error","error":"something went wrong"}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	_, err := s.createDashboard(context.Background(), map[string]interface{}{"title": "Test"})
	if err == nil {
		t.Fatal("expected error for API error response, got nil")
	}
}

func TestUpdateDashboard_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			t.Errorf("expected PUT, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.updateDashboard(context.Background(), "some-uuid", map[string]interface{}{"title": "Updated"})
	if err != nil {
		t.Fatalf("updateDashboard failed: %v", err)
	}
}

func TestUpdateDashboard_HTTPError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.updateDashboard(context.Background(), "bad-uuid", map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for 404 response, got nil")
	}
}

func TestDeleteDashboardByUUID_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("expected DELETE, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.deleteDashboardByUUID(context.Background(), "some-uuid")
	if err != nil {
		t.Fatalf("deleteDashboardByUUID failed: %v", err)
	}
}

func TestDeleteDashboardByUUID_404IsIgnored(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	})
	s, _ := newSidecarWithServer(t, handler)

	// 404 should NOT return an error (dashboard already gone)
	err := s.deleteDashboardByUUID(context.Background(), "already-gone")
	if err != nil {
		t.Fatalf("expected 404 to be ignored, got: %v", err)
	}
}

func TestDeleteDashboardByUUID_500IsError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.deleteDashboardByUUID(context.Background(), "some-uuid")
	if err == nil {
		t.Fatal("expected error for 500 response, got nil")
	}
}

// ============================================================================
// Alert API tests
// ============================================================================

func TestCreateAlert_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"alert-id-456"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	id, err := s.createAlert(context.Background(), map[string]interface{}{"alert": "TestAlert"})
	if err != nil {
		t.Fatalf("createAlert failed: %v", err)
	}
	if id != "alert-id-456" {
		t.Errorf("id = %q, want %q", id, "alert-id-456")
	}
}

func TestCreateAlert_HTTPError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "bad request", http.StatusBadRequest)
	})
	s, _ := newSidecarWithServer(t, handler)

	_, err := s.createAlert(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for 400 response, got nil")
	}
}

func TestCreateAlert_APIErrorStatus(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"error","error":"invalid rule"}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	_, err := s.createAlert(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for API error, got nil")
	}
}

func TestUpdateAlert_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			t.Errorf("expected PUT, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.updateAlert(context.Background(), "alert-id-456", map[string]interface{}{"alert": "Updated"})
	if err != nil {
		t.Fatalf("updateAlert failed: %v", err)
	}
}

func TestUpdateAlert_HTTPError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.updateAlert(context.Background(), "some-id", map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for 500, got nil")
	}
}

func TestDeleteAlertByID_404IsIgnored(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.deleteAlertByID(context.Background(), "missing-id")
	if err != nil {
		t.Fatalf("expected 404 to be ignored, got: %v", err)
	}
}

func TestDeleteAlertByID_500IsError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.deleteAlertByID(context.Background(), "some-id")
	if err == nil {
		t.Fatal("expected error for 500, got nil")
	}
}

// ============================================================================
// Channel API tests
// ============================================================================

func TestCreateChannel_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"channel-id-789"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	id, err := s.createChannel(context.Background(), map[string]interface{}{"name": "slack-alerts"})
	if err != nil {
		t.Fatalf("createChannel failed: %v", err)
	}
	if id != "channel-id-789" {
		t.Errorf("id = %q, want %q", id, "channel-id-789")
	}
}

func TestCreateChannel_HTTPError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	_, err := s.createChannel(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for 500, got nil")
	}
}

func TestCreateChannel_APIErrorStatus(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"error","error":"invalid channel config"}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	_, err := s.createChannel(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for API error, got nil")
	}
}

func TestUpdateChannel_Success(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			t.Errorf("expected PUT, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.updateChannel(context.Background(), "channel-id-789", map[string]interface{}{"name": "updated"})
	if err != nil {
		t.Fatalf("updateChannel failed: %v", err)
	}
}

func TestUpdateChannel_HTTPError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.updateChannel(context.Background(), "bad-id", map[string]interface{}{})
	if err == nil {
		t.Fatal("expected error for 500, got nil")
	}
}

func TestDeleteChannelByID_404IsIgnored(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.deleteChannelByID(context.Background(), "missing-id")
	if err != nil {
		t.Fatalf("expected 404 to be ignored, got: %v", err)
	}
}

func TestDeleteChannelByID_500IsError(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	})
	s, _ := newSidecarWithServer(t, handler)

	err := s.deleteChannelByID(context.Background(), "some-id")
	if err == nil {
		t.Fatal("expected error for 500, got nil")
	}
}

// ============================================================================
// State persistence tests (loadState / saveState)
// ============================================================================

func TestLoadState_NotFound(t *testing.T) {
	s := newSidecarForExtract()
	// fake clientset has no ConfigMaps — loadState should succeed (start fresh)
	err := s.loadState(context.Background())
	if err != nil {
		t.Fatalf("loadState with missing state CM should succeed, got: %v", err)
	}
}

func TestLoadState_Valid(t *testing.T) {
	fakeClient := fake.NewClientset()
	state := StateStore{
		"uid-1": {UUID: "dash-uuid-1", ContentHash: "hash1", Name: "my-dash", Namespace: "default", SyncedAt: "2025-01-01T00:00:00Z"},
	}
	alertState := AlertStateStore{
		"uid-2": {ID: "alert-id-1", ContentHash: "hash2", Name: "my-alert", Namespace: "default", SyncedAt: "2025-01-01T00:00:00Z"},
	}
	channelState := ChannelStateStore{
		"uid-3": {ID: "channel-id-1", ContentHash: "hash3", Name: "my-channel", Namespace: "default", SyncedAt: "2025-01-01T00:00:00Z"},
	}

	stateJSON, _ := json.Marshal(state)
	alertStateJSON, _ := json.Marshal(alertState)
	channelStateJSON, _ := json.Marshal(channelState)

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      stateConfigMapName,
			Namespace: "signoz",
		},
		Data: map[string]string{
			"state":        string(stateJSON),
			"alertState":   string(alertStateJSON),
			"channelState": string(channelStateJSON),
		},
	}
	_, err := fakeClient.CoreV1().ConfigMaps("signoz").Create(context.Background(), cm, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("failed to create test ConfigMap: %v", err)
	}

	s := &Sidecar{
		config:       Config{StateNamespace: "signoz"},
		clientset:    fakeClient,
		httpClient:   &http.Client{},
		logger:       newTestLogger(),
		state:        make(StateStore),
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}

	if err := s.loadState(context.Background()); err != nil {
		t.Fatalf("loadState failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()

	if len(s.state) != 1 {
		t.Errorf("expected 1 dashboard state, got %d", len(s.state))
	}
	if s.state["uid-1"].UUID != "dash-uuid-1" {
		t.Errorf("state uid-1 UUID = %q, want %q", s.state["uid-1"].UUID, "dash-uuid-1")
	}
	if len(s.alertState) != 1 {
		t.Errorf("expected 1 alert state, got %d", len(s.alertState))
	}
	if len(s.channelState) != 1 {
		t.Errorf("expected 1 channel state, got %d", len(s.channelState))
	}
}

func TestLoadState_InvalidJSON(t *testing.T) {
	fakeClient := fake.NewClientset()
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      stateConfigMapName,
			Namespace: "signoz",
		},
		Data: map[string]string{
			"state": `{invalid`,
		},
	}
	fakeClient.CoreV1().ConfigMaps("signoz").Create(context.Background(), cm, metav1.CreateOptions{})

	s := &Sidecar{
		config:       Config{StateNamespace: "signoz"},
		clientset:    fakeClient,
		httpClient:   &http.Client{},
		logger:       newTestLogger(),
		state:        make(StateStore),
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}

	err := s.loadState(context.Background())
	if err == nil {
		t.Fatal("expected error for invalid JSON state, got nil")
	}
}

func TestSaveState_CreatesConfigMap(t *testing.T) {
	fakeClient := fake.NewClientset()
	s := &Sidecar{
		config:       Config{StateNamespace: "signoz"},
		clientset:    fakeClient,
		httpClient:   &http.Client{},
		logger:       newTestLogger(),
		state:        make(StateStore),
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}
	s.state["uid-abc"] = DashboardState{
		UUID:        "dash-abc",
		ContentHash: "hash-xyz",
		Name:        "test-dash",
		Namespace:   "default",
		SyncedAt:    "2025-01-01T00:00:00Z",
	}

	if err := s.saveState(context.Background()); err != nil {
		t.Fatalf("saveState failed: %v", err)
	}

	cm, err := fakeClient.CoreV1().ConfigMaps("signoz").Get(context.Background(), stateConfigMapName, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("failed to get state ConfigMap after save: %v", err)
	}

	var savedState StateStore
	if err := json.Unmarshal([]byte(cm.Data["state"]), &savedState); err != nil {
		t.Fatalf("failed to parse saved state: %v", err)
	}
	if savedState["uid-abc"].UUID != "dash-abc" {
		t.Errorf("saved UUID = %q, want %q", savedState["uid-abc"].UUID, "dash-abc")
	}
}

func TestSaveState_UpdatesExistingConfigMap(t *testing.T) {
	fakeClient := fake.NewClientset()
	// Pre-create the state ConfigMap
	initial := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      stateConfigMapName,
			Namespace: "signoz",
		},
		Data: map[string]string{
			"state":        `{}`,
			"alertState":   `{}`,
			"channelState": `{}`,
		},
	}
	_, err := fakeClient.CoreV1().ConfigMaps("signoz").Create(context.Background(), initial, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &Sidecar{
		config:       Config{StateNamespace: "signoz"},
		clientset:    fakeClient,
		httpClient:   &http.Client{},
		logger:       newTestLogger(),
		state:        StateStore{"uid-new": {UUID: "new-uuid", ContentHash: "h", Name: "n", Namespace: "ns", SyncedAt: "t"}},
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}

	if err := s.saveState(context.Background()); err != nil {
		t.Fatalf("saveState failed: %v", err)
	}

	cm, err := fakeClient.CoreV1().ConfigMaps("signoz").Get(context.Background(), stateConfigMapName, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get: %v", err)
	}

	var savedState StateStore
	if err := json.Unmarshal([]byte(cm.Data["state"]), &savedState); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, ok := savedState["uid-new"]; !ok {
		t.Error("expected uid-new in saved state")
	}
}

// ============================================================================
// substituteSecrets tests
// ============================================================================

func TestSubstituteSecrets_ReplacesPlaceholders(t *testing.T) {
	fakeClient := fake.NewClientset()
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-secret",
			Namespace: "default",
		},
		Data: map[string][]byte{
			"WEBHOOK_URL": []byte("https://hooks.slack.com/services/ABC"),
			"TOKEN":       []byte("my-token-value"),
		},
	}
	_, err := fakeClient.CoreV1().Secrets("default").Create(context.Background(), secret, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &Sidecar{
		config:    Config{},
		clientset: fakeClient,
		logger:    newTestLogger(),
	}

	jsonData := []byte(`{"url":"${WEBHOOK_URL}","token":"${TOKEN}"}`)
	result, err := s.substituteSecrets(context.Background(), jsonData, "my-secret", "default")
	if err != nil {
		t.Fatalf("substituteSecrets failed: %v", err)
	}

	var parsed map[string]string
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v (raw: %s)", err, result)
	}
	if parsed["url"] != "https://hooks.slack.com/services/ABC" {
		t.Errorf("url = %q, want %q", parsed["url"], "https://hooks.slack.com/services/ABC")
	}
	if parsed["token"] != "my-token-value" {
		t.Errorf("token = %q, want %q", parsed["token"], "my-token-value")
	}
}

func TestSubstituteSecrets_NamespacedSecretRef(t *testing.T) {
	fakeClient := fake.NewClientset()
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cross-ns-secret",
			Namespace: "secrets-ns",
		},
		Data: map[string][]byte{
			"KEY": []byte("cross-ns-value"),
		},
	}
	_, err := fakeClient.CoreV1().Secrets("secrets-ns").Create(context.Background(), secret, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &Sidecar{
		config:    Config{},
		clientset: fakeClient,
		logger:    newTestLogger(),
	}

	jsonData := []byte(`{"key":"${KEY}"}`)
	result, err := s.substituteSecrets(context.Background(), jsonData, "secrets-ns/cross-ns-secret", "default")
	if err != nil {
		t.Fatalf("substituteSecrets failed: %v", err)
	}

	var parsed map[string]string
	if err := json.Unmarshal(result, &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v (raw: %s)", err, result)
	}
	if parsed["key"] != "cross-ns-value" {
		t.Errorf("key = %q, want %q", parsed["key"], "cross-ns-value")
	}
}

func TestSubstituteSecrets_MissingSecret(t *testing.T) {
	s := &Sidecar{
		config:    Config{},
		clientset: fake.NewClientset(),
		logger:    newTestLogger(),
	}

	_, err := s.substituteSecrets(context.Background(), []byte(`{}`), "missing-secret", "default")
	if err == nil {
		t.Fatal("expected error for missing secret, got nil")
	}
}

func TestSubstituteSecrets_NoPlaceholders(t *testing.T) {
	fakeClient := fake.NewClientset()
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-secret",
			Namespace: "default",
		},
		Data: map[string][]byte{
			"KEY": []byte("value"),
		},
	}
	_, err := fakeClient.CoreV1().Secrets("default").Create(context.Background(), secret, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &Sidecar{
		config:    Config{},
		clientset: fakeClient,
		logger:    newTestLogger(),
	}

	input := []byte(`{"static":"value"}`)
	result, err := s.substituteSecrets(context.Background(), input, "my-secret", "default")
	if err != nil {
		t.Fatalf("substituteSecrets failed: %v", err)
	}
	if string(result) != string(input) {
		t.Errorf("expected unchanged result %q, got %q", input, result)
	}
}

// ============================================================================
// syncDashboard tests — hash-based skip logic
// ============================================================================

func TestSyncDashboard_SkipsWhenUnchanged(t *testing.T) {
	callCount := 0
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-dash",
			Namespace: "default",
			UID:       types.UID("uid-test-skip"),
		},
		Data: map[string]string{
			"dashboard.json": `{"title":"Test"}`,
		},
	}

	// Pre-populate state with matching hash
	contentHash := computeConfigHash([]byte(`{"title":"Test"}`), cm.Annotations)
	s.state["uid-test-skip"] = DashboardState{
		UUID:        "existing-uuid",
		ContentHash: contentHash,
		Name:        cm.Name,
		Namespace:   cm.Namespace,
	}

	err := s.syncDashboard(context.Background(), cm, false)
	if err != nil {
		t.Fatalf("syncDashboard failed: %v", err)
	}
	if callCount > 0 {
		t.Errorf("expected no API calls when content unchanged, got %d", callCount)
	}
}

func TestSyncDashboard_CreatesNewDashboard(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST for create, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"uuid":"new-dash-uuid","data":{}}}`)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "new-dash",
			Namespace: "default",
			UID:       types.UID("uid-new-dash"),
		},
		Data: map[string]string{
			"dashboard.json": `{"title":"New Dashboard","tags":[]}`,
		},
	}

	err := s.syncDashboard(context.Background(), cm, false)
	if err != nil {
		t.Fatalf("syncDashboard failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if state, ok := s.state["uid-new-dash"]; !ok {
		t.Error("expected state entry for new dashboard")
	} else if state.UUID != "new-dash-uuid" {
		t.Errorf("state UUID = %q, want %q", state.UUID, "new-dash-uuid")
	}
}

func TestSyncDashboard_UpdatesExistingDashboard(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			t.Errorf("expected PUT for update, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "existing-dash",
			Namespace: "default",
			UID:       types.UID("uid-existing-dash"),
		},
		Data: map[string]string{
			"dashboard.json": `{"title":"Updated Dashboard"}`,
		},
	}

	// Pre-populate state with old hash
	s.state["uid-existing-dash"] = DashboardState{
		UUID:        "existing-dash-uuid",
		ContentHash: "old-hash-different",
		Name:        cm.Name,
		Namespace:   cm.Namespace,
	}

	err := s.syncDashboard(context.Background(), cm, false)
	if err != nil {
		t.Fatalf("syncDashboard update failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if state, ok := s.state["uid-existing-dash"]; !ok {
		t.Error("expected state entry to remain")
	} else if state.UUID != "existing-dash-uuid" {
		t.Errorf("UUID changed unexpectedly to %q", state.UUID)
	}
}

func TestSyncDashboard_SetsNameFromAnnotation(t *testing.T) {
	var receivedPayload map[string]interface{}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedPayload)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"uuid":"uuid-from-annotation","data":{}}}`)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "dash-with-annotation",
			Namespace: "default",
			UID:       types.UID("uid-annotation-dash"),
			Annotations: map[string]string{
				dashboardNameKey: "Custom Dashboard Title",
			},
		},
		Data: map[string]string{
			"dashboard.json": `{"title":"Original Title"}`,
		},
	}

	if err := s.syncDashboard(context.Background(), cm, false); err != nil {
		t.Fatalf("syncDashboard failed: %v", err)
	}

	if title, ok := receivedPayload["title"].(string); !ok || title != "Custom Dashboard Title" {
		t.Errorf("title = %q, want %q", title, "Custom Dashboard Title")
	}
}

func TestSyncDashboard_InvalidJSON(t *testing.T) {
	s, _ := newSidecarWithServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "bad-dash",
			Namespace: "default",
			UID:       types.UID("uid-bad"),
		},
		Data: map[string]string{
			"dashboard.json": `{invalid json`,
		},
	}

	err := s.syncDashboard(context.Background(), cm, false)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

func TestSyncDashboard_ForceUpdateCallsAPIEvenWhenUnchanged(t *testing.T) {
	callCount := 0
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		if r.Method == http.MethodPut {
			w.WriteHeader(http.StatusOK)
		}
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "force-dash",
			Namespace: "default",
			UID:       types.UID("uid-force-dash"),
		},
		Data: map[string]string{
			"dashboard.json": `{"title":"Force Update"}`,
		},
	}

	// Pre-populate with matching hash — but forceUpdate=true should still call API
	contentHash := computeConfigHash([]byte(`{"title":"Force Update"}`), cm.Annotations)
	s.state["uid-force-dash"] = DashboardState{
		UUID:        "force-dash-uuid",
		ContentHash: contentHash,
		Name:        cm.Name,
		Namespace:   cm.Namespace,
	}

	err := s.syncDashboard(context.Background(), cm, true)
	if err != nil {
		t.Fatalf("syncDashboard force update failed: %v", err)
	}
	if callCount == 0 {
		t.Error("expected API call for forced update")
	}
}

// ============================================================================
// syncAlert tests
// ============================================================================

func TestSyncAlert_CreatesNewAlert(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST for create, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"new-alert-id"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-alert",
			Namespace: "default",
			UID:       types.UID("uid-alert-new"),
		},
		Data: map[string]string{
			"alert.json": `{"alert":"HighCPU","expr":"cpu > 90"}`,
		},
	}

	if err := s.syncAlert(context.Background(), cm, false); err != nil {
		t.Fatalf("syncAlert failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if state, ok := s.alertState["uid-alert-new"]; !ok {
		t.Error("expected alert state entry")
	} else if state.ID != "new-alert-id" {
		t.Errorf("alert ID = %q, want %q", state.ID, "new-alert-id")
	}
}

func TestSyncAlert_SkipsWhenUnchanged(t *testing.T) {
	callCount := 0
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
	})
	s, _ := newSidecarWithServer(t, handler)

	alertJSON := []byte(`{"alert":"HighCPU"}`)
	contentHash := hashContent(alertJSON)

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "skip-alert",
			Namespace: "default",
			UID:       types.UID("uid-skip-alert"),
		},
		Data: map[string]string{
			"alert.json": string(alertJSON),
		},
	}

	s.alertState["uid-skip-alert"] = AlertState{
		ID:          "existing-alert-id",
		ContentHash: contentHash,
		Name:        cm.Name,
		Namespace:   cm.Namespace,
	}

	if err := s.syncAlert(context.Background(), cm, false); err != nil {
		t.Fatalf("syncAlert failed: %v", err)
	}
	if callCount > 0 {
		t.Errorf("expected no API calls, got %d", callCount)
	}
}

func TestSyncAlert_AppliesAnnotationOverrides(t *testing.T) {
	var receivedPayload map[string]interface{}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedPayload)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"annotated-alert-id"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "annotated-alert",
			Namespace: "default",
			UID:       types.UID("uid-annotated-alert"),
			Annotations: map[string]string{
				alertNameKey:     "Overridden Alert Name",
				alertSeverityKey: "critical",
				alertChannelsKey: "slack,pagerduty",
			},
		},
		Data: map[string]string{
			"alert.json": `{"alert":"OriginalName","expr":"rate > 0"}`,
		},
	}

	if err := s.syncAlert(context.Background(), cm, false); err != nil {
		t.Fatalf("syncAlert failed: %v", err)
	}

	if name, ok := receivedPayload["alert"].(string); !ok || name != "Overridden Alert Name" {
		t.Errorf("alert name = %q, want %q", name, "Overridden Alert Name")
	}
	if severity, ok := receivedPayload["severity"].(string); !ok || severity != "critical" {
		t.Errorf("severity = %q, want %q", severity, "critical")
	}
	if channels, ok := receivedPayload["preferredChannels"].([]interface{}); !ok || len(channels) != 2 {
		t.Errorf("preferredChannels = %v, want 2 entries", receivedPayload["preferredChannels"])
	}
}

func TestSyncAlert_InvalidJSON(t *testing.T) {
	s, _ := newSidecarWithServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "bad-alert",
			Namespace: "default",
			UID:       types.UID("uid-bad-alert"),
		},
		Data: map[string]string{
			"alert.json": `{bad json`,
		},
	}

	err := s.syncAlert(context.Background(), cm, false)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

// ============================================================================
// syncChannel tests
// ============================================================================

func TestSyncChannel_CreatesNewChannel(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST for create, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"new-channel-id"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-channel",
			Namespace: "default",
			UID:       types.UID("uid-channel-new"),
		},
		Data: map[string]string{
			"channel.json": `{"name":"slack-infra","type":"slack"}`,
		},
	}

	if err := s.syncChannel(context.Background(), cm, false); err != nil {
		t.Fatalf("syncChannel failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if state, ok := s.channelState["uid-channel-new"]; !ok {
		t.Error("expected channel state entry")
	} else if state.ID != "new-channel-id" {
		t.Errorf("channel ID = %q, want %q", state.ID, "new-channel-id")
	}
}

func TestSyncChannel_SkipsWhenUnchanged(t *testing.T) {
	callCount := 0
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
	})
	s, _ := newSidecarWithServer(t, handler)

	channelJSON := []byte(`{"name":"slack"}`)
	contentHash := hashContent(channelJSON)

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "skip-channel",
			Namespace: "default",
			UID:       types.UID("uid-skip-channel"),
		},
		Data: map[string]string{
			"channel.json": string(channelJSON),
		},
	}

	s.channelState["uid-skip-channel"] = ChannelState{
		ID:          "existing-channel-id",
		ContentHash: contentHash,
		Name:        cm.Name,
		Namespace:   cm.Namespace,
	}

	if err := s.syncChannel(context.Background(), cm, false); err != nil {
		t.Fatalf("syncChannel failed: %v", err)
	}
	if callCount > 0 {
		t.Errorf("expected no API calls, got %d", callCount)
	}
}

func TestSyncChannel_WithSecretSubstitution(t *testing.T) {
	var receivedPayload map[string]interface{}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedPayload)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"channel-with-secret"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)

	fakeClient := fake.NewClientset()
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "webhook-secret",
			Namespace: "default",
		},
		Data: map[string][]byte{
			"WEBHOOK_URL": []byte("https://hooks.slack.com/T123/B456/XYZ"),
		},
	}
	fakeClient.CoreV1().Secrets("default").Create(context.Background(), secret, metav1.CreateOptions{})
	s.clientset = fakeClient

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "slack-channel",
			Namespace: "default",
			UID:       types.UID("uid-secret-channel"),
			Annotations: map[string]string{
				secretRefKey: "webhook-secret",
			},
		},
		Data: map[string]string{
			"channel.json": `{"name":"slack","url":"${WEBHOOK_URL}"}`,
		},
	}

	if err := s.syncChannel(context.Background(), cm, false); err != nil {
		t.Fatalf("syncChannel with secrets failed: %v", err)
	}

	if url, ok := receivedPayload["url"].(string); !ok || url != "https://hooks.slack.com/T123/B456/XYZ" {
		t.Errorf("url = %q, want %q", url, "https://hooks.slack.com/T123/B456/XYZ")
	}
}

func TestSyncChannel_NameFromAnnotation(t *testing.T) {
	var receivedPayload map[string]interface{}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedPayload)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"success","data":{"id":"channel-named"}}`)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-channel",
			Namespace: "default",
			UID:       types.UID("uid-channel-named"),
			Annotations: map[string]string{
				channelNameKey: "Custom Channel Name",
			},
		},
		Data: map[string]string{
			"channel.json": `{"name":"original-name","type":"slack"}`,
		},
	}

	if err := s.syncChannel(context.Background(), cm, false); err != nil {
		t.Fatalf("syncChannel failed: %v", err)
	}

	if name, ok := receivedPayload["name"].(string); !ok || name != "Custom Channel Name" {
		t.Errorf("channel name = %q, want %q", name, "Custom Channel Name")
	}
}

// ============================================================================
// deleteDashboard / deleteAlert / deleteChannel tests
// ============================================================================

func TestDeleteDashboard_NotInState(t *testing.T) {
	s, _ := newSidecarWithServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("unexpected API call")
	}))

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "unknown",
			Namespace: "default",
			UID:       types.UID("uid-not-in-state"),
		},
	}

	err := s.deleteDashboard(context.Background(), cm)
	if err != nil {
		t.Fatalf("expected no error for unknown dashboard, got: %v", err)
	}
}

func TestDeleteDashboard_InState(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("expected DELETE, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "managed-dash",
			Namespace: "default",
			UID:       types.UID("uid-managed-dash"),
		},
	}

	s.state["uid-managed-dash"] = DashboardState{
		UUID:      "delete-me-uuid",
		Name:      cm.Name,
		Namespace: cm.Namespace,
	}

	if err := s.deleteDashboard(context.Background(), cm); err != nil {
		t.Fatalf("deleteDashboard failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if _, ok := s.state["uid-managed-dash"]; ok {
		t.Error("expected state entry to be removed after deletion")
	}
}

func TestDeleteAlert_NotInState(t *testing.T) {
	s, _ := newSidecarWithServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("unexpected API call")
	}))

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			UID: types.UID("uid-not-in-alert-state"),
		},
	}

	if err := s.deleteAlert(context.Background(), cm); err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
}

func TestDeleteAlert_InState(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("expected DELETE, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "managed-alert",
			Namespace: "default",
			UID:       types.UID("uid-managed-alert"),
		},
	}

	s.alertState["uid-managed-alert"] = AlertState{
		ID:        "delete-me-id",
		Name:      cm.Name,
		Namespace: cm.Namespace,
	}

	if err := s.deleteAlert(context.Background(), cm); err != nil {
		t.Fatalf("deleteAlert failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if _, ok := s.alertState["uid-managed-alert"]; ok {
		t.Error("expected alert state entry to be removed")
	}
}

func TestDeleteChannel_NotInState(t *testing.T) {
	s, _ := newSidecarWithServer(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("unexpected API call")
	}))

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			UID: types.UID("uid-not-in-channel-state"),
		},
	}

	if err := s.deleteChannel(context.Background(), cm); err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
}

func TestDeleteChannel_InState(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			t.Errorf("expected DELETE, got %s", r.Method)
		}
		w.WriteHeader(http.StatusOK)
	})
	s, _ := newSidecarWithServer(t, handler)
	s.clientset = fake.NewClientset()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "managed-channel",
			Namespace: "default",
			UID:       types.UID("uid-managed-channel"),
		},
	}

	s.channelState["uid-managed-channel"] = ChannelState{
		ID:        "delete-me-channel-id",
		Name:      cm.Name,
		Namespace: cm.Namespace,
	}

	if err := s.deleteChannel(context.Background(), cm); err != nil {
		t.Fatalf("deleteChannel failed: %v", err)
	}

	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	if _, ok := s.channelState["uid-managed-channel"]; ok {
		t.Error("expected channel state entry to be removed")
	}
}
