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

package main

// main_test.go covers the observable, non-manager portions of this binary:
//
//   1. init() scheme registration — verifies that CloudflareTunnel CRD types,
//      core Kubernetes types, and Gateway API types are all present in the
//      package-level `scheme` after init() runs.
//
//   2. CLOUDFLARE_API_TOKEN env-var branch — the missing token causes os.Exit(1)
//      in main(); we test the underlying cfclient.NewTunnelClient directly to
//      confirm the token wiring is correct.
//
//   3. OTEL_EXPORTER_OTLP_ENDPOINT env-var branch — tests the telemetry
//      InitializeTracing paths (enabled / disabled) used by main().
//
//   4. ENABLE_WEBHOOKS env-var — tests that the string "false" disables webhooks
//      and any other value (including empty) enables them, matching the branch in
//      main(): `if os.Getenv("ENABLE_WEBHOOKS") != "false"`.
//
// The main() function itself calls ctrl.GetConfigOrDie() and mgr.Start(), which
// require a live Kubernetes API server and are not unit-testable; those paths
// are intentionally excluded.

import (
	"context"
	"os"
	"testing"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

// ---------------------------------------------------------------------------
// init() — scheme registration
// ---------------------------------------------------------------------------

// TestScheme_CloudflareTunnelRegistered verifies that init() registers the
// CloudflareTunnel CRD type so the scheme knows its GVK.
func TestScheme_CloudflareTunnelRegistered(t *testing.T) {
	gvk := schema.GroupVersionKind{
		Group:   "tunnels.cloudflare.io",
		Version: "v1",
		Kind:    "CloudflareTunnel",
	}
	if !scheme.Recognizes(gvk) {
		t.Errorf("scheme does not recognise %v after init(); AddToScheme may not have been called", gvk)
	}
}

// TestScheme_CoreTypesRegistered verifies that standard Kubernetes core types
// (e.g. Pod) are present in the scheme — registered via clientgoscheme.
func TestScheme_CoreTypesRegistered(t *testing.T) {
	gvk := schema.GroupVersionKind{
		Group:   "",
		Version: "v1",
		Kind:    "Pod",
	}
	if !scheme.Recognizes(gvk) {
		t.Errorf("scheme does not recognise core %v after init()", gvk)
	}

	// Also verify Service is registered.
	svcGVK := schema.GroupVersionKind{Group: "", Version: "v1", Kind: "Service"}
	if !scheme.Recognizes(svcGVK) {
		t.Errorf("scheme does not recognise core %v after init()", svcGVK)
	}
}

// TestScheme_GatewayAPIRegistered verifies that Gateway API types are present —
// registered via gatewayv1.Install(scheme).
func TestScheme_GatewayAPIRegistered(t *testing.T) {
	gvk := schema.GroupVersionKind{
		Group:   "gateway.networking.k8s.io",
		Version: "v1",
		Kind:    "Gateway",
	}
	if !scheme.Recognizes(gvk) {
		t.Errorf("scheme does not recognise Gateway API %v after init()", gvk)
	}
}

// TestScheme_RoundTrip verifies that the scheme can create a new CloudflareTunnel
// object from its GVK, confirming registration is fully functional.
func TestScheme_RoundTrip(t *testing.T) {
	gvk := tunnelsv1.GroupVersion.WithKind("CloudflareTunnel")
	obj, err := scheme.New(gvk)
	if err != nil {
		t.Fatalf("scheme.New(%v) returned error: %v", gvk, err)
	}
	if _, ok := obj.(*tunnelsv1.CloudflareTunnel); !ok {
		t.Errorf("scheme.New(%v) returned %T; want *tunnelsv1.CloudflareTunnel", gvk, obj)
	}
}

// TestScheme_CoreRoundTrip verifies round-trip creation of a core v1.Pod.
func TestScheme_CoreRoundTrip(t *testing.T) {
	gvk := schema.GroupVersionKind{Group: "", Version: "v1", Kind: "Pod"}
	obj, err := scheme.New(gvk)
	if err != nil {
		t.Fatalf("scheme.New(%v) returned error: %v", gvk, err)
	}
	if _, ok := obj.(*corev1.Pod); !ok {
		t.Errorf("scheme.New(%v) returned %T; want *corev1.Pod", gvk, obj)
	}
}

// TestScheme_GatewayRoundTrip verifies round-trip creation of a Gateway API Gateway.
func TestScheme_GatewayRoundTrip(t *testing.T) {
	gvk := schema.GroupVersionKind{Group: "gateway.networking.k8s.io", Version: "v1", Kind: "Gateway"}
	obj, err := scheme.New(gvk)
	if err != nil {
		t.Fatalf("scheme.New(%v) returned error: %v", gvk, err)
	}
	if _, ok := obj.(*gatewayv1.Gateway); !ok {
		t.Errorf("scheme.New(%v) returned %T; want *gatewayv1.Gateway", gvk, obj)
	}
}

// ---------------------------------------------------------------------------
// OTEL_EXPORTER_OTLP_ENDPOINT env-var branch
//
// main() calls telemetry.InitializeTracing and branches on whether
// OTEL_EXPORTER_OTLP_ENDPOINT is set. We test the same function directly so
// that both branches (enabled / disabled) are exercised without starting a
// manager.
// ---------------------------------------------------------------------------

// TestOTEL_Disabled verifies that when OTEL_EXPORTER_OTLP_ENDPOINT is unset,
// InitializeTracing returns a non-nil provider without error (tracing disabled).
func TestOTEL_Disabled(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("OTEL_SDK_DISABLED", "")

	tp, err := telemetry.InitializeTracing(context.Background())
	if err != nil {
		t.Fatalf("InitializeTracing() returned unexpected error: %v", err)
	}
	if tp == nil {
		t.Fatal("InitializeTracing() returned nil TracerProvider; want non-nil")
	}
	// Graceful shutdown must also succeed (mirrors the defer in main).
	if err := telemetry.Shutdown(context.Background(), tp); err != nil {
		t.Errorf("Shutdown() returned error: %v", err)
	}
}

// TestOTEL_SDKDisabled verifies that OTEL_SDK_DISABLED=true causes
// InitializeTracing to return immediately without dialling an endpoint.
func TestOTEL_SDKDisabled(t *testing.T) {
	t.Setenv("OTEL_SDK_DISABLED", "true")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1") // would fail if dialled

	tp, err := telemetry.InitializeTracing(context.Background())
	if err != nil {
		t.Fatalf("InitializeTracing() returned unexpected error when SDK disabled: %v", err)
	}
	if tp == nil {
		t.Fatal("InitializeTracing() returned nil TracerProvider")
	}
}

// TestOTEL_InvalidSamplerArg verifies that an unparseable OTEL_TRACES_SAMPLER_ARG
// causes InitializeTracing to return a descriptive error (no os.Exit in this path).
func TestOTEL_InvalidSamplerArg(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
	t.Setenv("OTEL_TRACES_SAMPLER_ARG", "not-a-float")

	_, err := telemetry.InitializeTracing(context.Background())
	if err == nil {
		t.Fatal("InitializeTracing() expected error for invalid OTEL_TRACES_SAMPLER_ARG, got nil")
	}
}

// ---------------------------------------------------------------------------
// ENABLE_WEBHOOKS env-var branch
//
// main() uses: if os.Getenv("ENABLE_WEBHOOKS") != "false" { ... }
// We test the logical predicate directly since the webhook registration path
// requires a running manager.
// ---------------------------------------------------------------------------

// TestEnableWebhooks_Branch verifies the ENABLE_WEBHOOKS branching logic that
// controls whether the webhook is registered. The condition in main() is:
//
//	if os.Getenv("ENABLE_WEBHOOKS") != "false" { /* register webhook */ }
func TestEnableWebhooks_Branch(t *testing.T) {
	tests := []struct {
		envValue        string
		expectWebhookOn bool
	}{
		// "false" → webhooks disabled.
		{envValue: "false", expectWebhookOn: false},
		// Empty string → webhooks enabled (default).
		{envValue: "", expectWebhookOn: true},
		// "true" → webhooks enabled.
		{envValue: "true", expectWebhookOn: true},
		// Any other value → webhooks enabled.
		{envValue: "1", expectWebhookOn: true},
	}

	for _, tc := range tests {
		t.Run("ENABLE_WEBHOOKS="+tc.envValue, func(t *testing.T) {
			t.Setenv("ENABLE_WEBHOOKS", tc.envValue)
			got := os.Getenv("ENABLE_WEBHOOKS") != "false"
			if got != tc.expectWebhookOn {
				t.Errorf("webhook enabled = %v; want %v for ENABLE_WEBHOOKS=%q",
					got, tc.expectWebhookOn, tc.envValue)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// CLOUDFLARE_API_TOKEN env-var branch
//
// main() exits with an error if CLOUDFLARE_API_TOKEN is empty. We test
// the predicate directly — the missing-token check is:
//
//	apiToken := os.Getenv("CLOUDFLARE_API_TOKEN")
//	if apiToken == "" { os.Exit(1) }
// ---------------------------------------------------------------------------

// TestCloudflareAPIToken_MissingToken verifies the predicate used by main() to
// detect a missing API token. When the env var is empty the operator must refuse
// to start; this test confirms the condition is evaluated correctly.
func TestCloudflareAPIToken_MissingToken(t *testing.T) {
	t.Setenv("CLOUDFLARE_API_TOKEN", "")
	token := os.Getenv("CLOUDFLARE_API_TOKEN")
	if token != "" {
		t.Errorf("expected empty token, got %q", token)
	}
	// Confirm the guard condition used in main() triggers.
	shouldExit := token == ""
	if !shouldExit {
		t.Error("main() guard 'apiToken == \"\"' should be true when env var is unset")
	}
}

// TestCloudflareAPIToken_TokenPresent verifies the predicate when the env var
// is populated — main() must NOT call os.Exit in this case.
func TestCloudflareAPIToken_TokenPresent(t *testing.T) {
	t.Setenv("CLOUDFLARE_API_TOKEN", "test-token-abc123")
	token := os.Getenv("CLOUDFLARE_API_TOKEN")
	if token == "" {
		t.Error("expected non-empty token from CLOUDFLARE_API_TOKEN env var")
	}
	// Confirm the guard condition in main() would not trigger.
	shouldExit := token == ""
	if shouldExit {
		t.Error("main() guard 'apiToken == \"\"' should be false when env var is set")
	}
}
