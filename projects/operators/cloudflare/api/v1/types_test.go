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

package v1

import (
	"bytes"
	"context"
	"encoding/json"
	"reflect"
	"strings"
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"
)

// fixedTime is a stable UTC timestamp with no sub-second precision, suitable
// for JSON round-trip tests. metav1.Time marshals to RFC3339 (second
// precision) so using time.Now() would lose nanoseconds across the round-trip.
var fixedTime = metav1.NewTime(time.Date(2025, 1, 15, 10, 30, 0, 0, time.UTC))

// --- TunnelIngress ---

// TestTunnelIngressJSONRoundTrip verifies TunnelIngress serializes and
// deserializes correctly, preserving all fields.
func TestTunnelIngressJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name    string
		ingress TunnelIngress
	}{
		{
			name:    "empty ingress",
			ingress: TunnelIngress{},
		},
		{
			name: "service only (catch-all)",
			ingress: TunnelIngress{
				Service: "http://backend.default.svc.cluster.local:8080",
			},
		},
		{
			name: "hostname and service",
			ingress: TunnelIngress{
				Hostname: "app.example.com",
				Service:  "http://app.default.svc.cluster.local:8080",
			},
		},
		{
			name: "hello_world service",
			ingress: TunnelIngress{
				Service: "hello_world",
			},
		},
		{
			name: "http_status service",
			ingress: TunnelIngress{
				Service: "http_status:404",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.ingress)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got TunnelIngress
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.ingress, got) {
				t.Errorf("round-trip mismatch: want %+v, got %+v", tt.ingress, got)
			}
		})
	}
}

// TestTunnelIngressJSONFieldNames verifies that TunnelIngress uses the
// expected JSON field names (hostname is omitempty, service is required).
func TestTunnelIngressJSONFieldNames(t *testing.T) {
	ingress := TunnelIngress{
		Hostname: "host.example.com",
		Service:  "http://svc:8080",
	}

	data, err := json.Marshal(ingress)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	if _, ok := raw["hostname"]; !ok {
		t.Error("expected JSON key 'hostname' to be present")
	}
	if _, ok := raw["service"]; !ok {
		t.Error("expected JSON key 'service' to be present")
	}

	// Verify hostname is omitted when empty (omitempty)
	empty := TunnelIngress{Service: "http://svc:8080"}
	emptyData, err := json.Marshal(empty)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var emptyRaw map[string]interface{}
	if err := json.Unmarshal(emptyData, &emptyRaw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}
	if _, ok := emptyRaw["hostname"]; ok {
		t.Error("expected JSON key 'hostname' to be omitted when empty (omitempty)")
	}
}

// --- SecretReference ---

// TestSecretReferenceJSONRoundTrip verifies SecretReference serializes and
// deserializes correctly.
func TestSecretReferenceJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name string
		ref  SecretReference
	}{
		{
			name: "name only",
			ref:  SecretReference{Name: "my-secret"},
		},
		{
			name: "name and default key",
			ref: SecretReference{
				Name: "tunnel-creds",
				Key:  "tunnel-secret",
			},
		},
		{
			name: "custom key",
			ref: SecretReference{
				Name: "tunnel-creds",
				Key:  "credentials.json",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.ref)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got SecretReference
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.ref, got) {
				t.Errorf("round-trip mismatch: want %+v, got %+v", tt.ref, got)
			}
		})
	}
}

// --- CloudflareTunnelSpec ---

// TestCloudflareTunnelSpecJSONRoundTrip verifies CloudflareTunnelSpec
// serializes and deserializes correctly with all field combinations.
func TestCloudflareTunnelSpecJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name string
		spec CloudflareTunnelSpec
	}{
		{
			name: "minimal spec",
			spec: CloudflareTunnelSpec{
				Name:      "my-tunnel",
				AccountID: "abc123",
			},
		},
		{
			name: "spec with configSource",
			spec: CloudflareTunnelSpec{
				Name:         "my-tunnel",
				AccountID:    "abc123",
				ConfigSource: "cloudflare",
			},
		},
		{
			name: "spec with single ingress rule",
			spec: CloudflareTunnelSpec{
				Name:      "my-tunnel",
				AccountID: "abc123",
				Ingress: []TunnelIngress{
					{Service: "http_status:404"},
				},
			},
		},
		{
			name: "spec with multiple ingress rules",
			spec: CloudflareTunnelSpec{
				Name:         "my-tunnel",
				AccountID:    "abc123",
				ConfigSource: "cloudflare",
				Ingress: []TunnelIngress{
					{Hostname: "api.example.com", Service: "https://api.default.svc:443"},
					{Hostname: "web.example.com", Service: "http://web.default.svc:80"},
					{Service: "http_status:404"},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.spec)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CloudflareTunnelSpec
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.spec, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.spec, got)
			}
		})
	}
}

// TestCloudflareTunnelSpecJSONFieldNames verifies the JSON field name for
// AccountID is "accountId" (camelCase as per kubebuilder annotation).
func TestCloudflareTunnelSpecJSONFieldNames(t *testing.T) {
	spec := CloudflareTunnelSpec{
		Name:         "my-tunnel",
		AccountID:    "abc123",
		ConfigSource: "cloudflare",
	}
	data, err := json.Marshal(spec)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	tests := []struct {
		key  string
		want string
	}{
		{"name", "my-tunnel"},
		{"accountId", "abc123"},
		{"configSource", "cloudflare"},
	}
	for _, tt := range tests {
		t.Run(tt.key, func(t *testing.T) {
			val, ok := raw[tt.key]
			if !ok {
				t.Errorf("expected JSON key %q to be present", tt.key)
				return
			}
			if val != tt.want {
				t.Errorf("JSON key %q = %q, want %q", tt.key, val, tt.want)
			}
		})
	}
}

// --- CloudflareTunnelStatus ---

// TestCloudflareTunnelStatusJSONRoundTrip verifies CloudflareTunnelStatus
// serializes and deserializes correctly.
func TestCloudflareTunnelStatusJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name   string
		status CloudflareTunnelStatus
	}{
		{
			name:   "empty status",
			status: CloudflareTunnelStatus{},
		},
		{
			name: "pending phase",
			status: CloudflareTunnelStatus{
				Phase:  "Pending",
				Active: false,
				Ready:  false,
			},
		},
		{
			name: "ready status",
			status: CloudflareTunnelStatus{
				Phase:              "Ready",
				TunnelID:           "tunnel-abc-123",
				SecretName:         "tunnel-creds",
				Active:             true,
				Ready:              true,
				ObservedGeneration: 3,
			},
		},
		{
			name: "failed status with error",
			status: CloudflareTunnelStatus{
				Phase:        "Failed",
				LastState:    "CreatingTunnel",
				ErrorMessage: "Cloudflare API returned 403",
				RetryCount:   2,
				Active:       false,
				Ready:        false,
			},
		},
		{
			name: "unknown phase with observed phase",
			status: CloudflareTunnelStatus{
				Phase:         "Unknown",
				ObservedPhase: "SomeUnrecognizedState",
				Active:        false,
				Ready:         false,
			},
		},
		{
			name: "status with conditions",
			status: CloudflareTunnelStatus{
				Phase:    "Ready",
				TunnelID: "tunnel-xyz-789",
				Active:   true,
				Ready:    true,
				Conditions: []metav1.Condition{
					{
						Type:               TypeReady,
						Status:             metav1.ConditionTrue,
						Reason:             ReasonTunnelConnected,
						Message:            "tunnel is active",
						LastTransitionTime: fixedTime,
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.status)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CloudflareTunnelStatus
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			// Use JSON byte comparison instead of reflect.DeepEqual to avoid
			// spurious failures caused by metav1.Time.UnmarshalJSON calling
			// pt.Local(), which produces a different *time.Location pointer
			// than time.UTC even when both represent UTC.
			gotData, err := json.Marshal(got)
			if err != nil {
				t.Fatalf("re-Marshal() error = %v", err)
			}
			if !bytes.Equal(data, gotData) {
				t.Errorf("round-trip mismatch:\n  want: %s\n  got:  %s", data, gotData)
			}
		})
	}
}

// TestCloudflareTunnelStatusPhaseValues verifies all documented phase values
// are distinct non-empty strings that can be stored in the Phase field.
func TestCloudflareTunnelStatusPhaseValues(t *testing.T) {
	phases := []string{
		"Pending",
		"CreatingTunnel",
		"CreatingSecret",
		"ConfiguringIngress",
		"Ready",
		"Failed",
		"DeletingTunnel",
		"Deleted",
		"Unknown",
	}

	seen := make(map[string]bool)
	for _, phase := range phases {
		t.Run(phase, func(t *testing.T) {
			if phase == "" {
				t.Error("phase must not be empty")
			}
			if seen[phase] {
				t.Errorf("duplicate phase value %q", phase)
			}
			seen[phase] = true

			s := CloudflareTunnelStatus{Phase: phase}
			if s.Phase != phase {
				t.Errorf("Phase field round-trip: want %q, got %q", phase, s.Phase)
			}
		})
	}
}

// TestCloudflareTunnelStatusActiveFalsePresent verifies that Active=false is
// preserved in JSON (the field has no omitempty tag).
func TestCloudflareTunnelStatusActiveFalsePresent(t *testing.T) {
	status := CloudflareTunnelStatus{Active: false, Ready: false}
	data, err := json.Marshal(status)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}
	if _, ok := raw["active"]; !ok {
		t.Error("expected JSON key 'active' to be present even when false (no omitempty)")
	}
	if _, ok := raw["ready"]; !ok {
		t.Error("expected JSON key 'ready' to be present even when false (no omitempty)")
	}
}

// --- AccessPolicyRule ---

// TestAccessPolicyRuleJSONRoundTrip verifies AccessPolicyRule serializes and
// deserializes correctly for all field combinations.
func TestAccessPolicyRuleJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name string
		rule AccessPolicyRule
	}{
		{
			name: "empty rule",
			rule: AccessPolicyRule{},
		},
		{
			name: "name only",
			rule: AccessPolicyRule{Name: "allow-engineers"},
		},
		{
			name: "email matchers",
			rule: AccessPolicyRule{
				Name:           "email-rule",
				Emails:         []string{"user@example.com", "admin@example.com"},
				EmailsEndingIn: []string{"@contractor.com"},
				EmailDomains:   []string{"example.com"},
			},
		},
		{
			name: "ip range matcher",
			rule: AccessPolicyRule{
				Name:     "vpn-rule",
				IPRanges: []string{"192.168.1.0/24", "10.0.0.1/32"},
			},
		},
		{
			name: "everyone matcher true",
			rule: AccessPolicyRule{
				Name:     "public-rule",
				Everyone: true,
			},
		},
		{
			name: "github matchers",
			rule: AccessPolicyRule{
				GitHubUsers:         []string{"octocat", "monalisa"},
				GitHubOrganizations: []string{"myorg"},
			},
		},
		{
			name: "country matcher",
			rule: AccessPolicyRule{
				Countries: []string{"US", "GB", "CA"},
			},
		},
		{
			name: "all fields populated",
			rule: AccessPolicyRule{
				Name:                "full-rule",
				EmailsEndingIn:      []string{"@example.com"},
				Emails:              []string{"user@example.com"},
				EmailDomains:        []string{"example.com"},
				IPRanges:            []string{"192.168.1.0/24"},
				Everyone:            false,
				GitHubUsers:         []string{"octocat"},
				GitHubOrganizations: []string{"myorg"},
				Countries:           []string{"US", "GB"},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.rule)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got AccessPolicyRule
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.rule, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.rule, got)
			}
		})
	}
}

// TestAccessPolicyRuleEveryoneFalseOmitted verifies that Everyone=false is
// omitted in JSON output (omitempty semantics).
func TestAccessPolicyRuleEveryoneFalseOmitted(t *testing.T) {
	rule := AccessPolicyRule{Name: "test", Everyone: false}
	data, err := json.Marshal(rule)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}
	if _, ok := raw["everyone"]; ok {
		t.Error("expected 'everyone' to be omitted when false (omitempty)")
	}
}

// TestAccessPolicyRuleJSONFieldNames verifies the JSON field names for
// AccessPolicyRule use camelCase as annotated.
func TestAccessPolicyRuleJSONFieldNames(t *testing.T) {
	rule := AccessPolicyRule{
		EmailsEndingIn:      []string{"@example.com"},
		GitHubUsers:         []string{"user"},
		GitHubOrganizations: []string{"org"},
		EmailDomains:        []string{"example.com"},
		IPRanges:            []string{"10.0.0.0/8"},
	}
	data, err := json.Marshal(rule)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}

	expectedKeys := []string{"emailsEndingIn", "githubUsers", "githubOrganizations", "emailDomains", "ipRanges"}
	for _, key := range expectedKeys {
		t.Run(key, func(t *testing.T) {
			if _, ok := raw[key]; !ok {
				t.Errorf("expected JSON key %q to be present", key)
			}
		})
	}
}

// --- CORSHeaders ---

// TestCORSHeadersJSONRoundTrip verifies CORSHeaders serializes and
// deserializes correctly.
func TestCORSHeadersJSONRoundTrip(t *testing.T) {
	maxAge := 3600
	tests := []struct {
		name string
		cors CORSHeaders
	}{
		{
			name: "empty cors",
			cors: CORSHeaders{},
		},
		{
			name: "allow all origins",
			cors: CORSHeaders{AllowAllOrigins: true},
		},
		{
			name: "specific origins and methods",
			cors: CORSHeaders{
				AllowedOrigins: []string{"https://example.com", "https://app.example.com"},
				AllowedMethods: []string{"GET", "POST", "PUT", "DELETE"},
				AllowedHeaders: []string{"Content-Type", "Authorization"},
			},
		},
		{
			name: "allow credentials",
			cors: CORSHeaders{
				AllowedOrigins:   []string{"https://example.com"},
				AllowCredentials: true,
			},
		},
		{
			name: "with max age",
			cors: CORSHeaders{
				AllowAllOrigins: true,
				MaxAge:          &maxAge,
			},
		},
		{
			name: "fully populated",
			cors: CORSHeaders{
				AllowAllOrigins:  true,
				AllowedOrigins:   []string{"https://example.com"},
				AllowedMethods:   []string{"GET", "POST"},
				AllowedHeaders:   []string{"Content-Type"},
				AllowCredentials: true,
				MaxAge:           &maxAge,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.cors)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CORSHeaders
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.cors, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.cors, got)
			}
		})
	}
}

// TestCORSHeadersMaxAgeNilOmitted verifies that MaxAge=nil is omitted in JSON.
func TestCORSHeadersMaxAgeNilOmitted(t *testing.T) {
	cors := CORSHeaders{AllowAllOrigins: true}
	data, err := json.Marshal(cors)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}
	if _, ok := raw["maxAge"]; ok {
		t.Error("expected 'maxAge' to be omitted when nil")
	}
}

// --- ApplicationConfig ---

// TestApplicationConfigJSONRoundTrip verifies ApplicationConfig serializes
// and deserializes correctly.
func TestApplicationConfigJSONRoundTrip(t *testing.T) {
	maxAge := 7200
	tests := []struct {
		name   string
		config ApplicationConfig
	}{
		{
			name:   "empty config",
			config: ApplicationConfig{},
		},
		{
			name: "basic config",
			config: ApplicationConfig{
				Name:            "My App",
				Domain:          "app.example.com",
				Type:            "self_hosted",
				SessionDuration: "24h",
			},
		},
		{
			name: "saas application",
			config: ApplicationConfig{
				Name:            "SaaS App",
				Type:            "saas",
				SessionDuration: "1h30m",
			},
		},
		{
			name: "config with cors",
			config: ApplicationConfig{
				Name:   "CORS App",
				Domain: "cors.example.com",
				Type:   "self_hosted",
				CORSHeaders: &CORSHeaders{
					AllowAllOrigins: true,
					MaxAge:          &maxAge,
				},
			},
		},
		{
			name: "all options enabled",
			config: ApplicationConfig{
				Name:                   "Full App",
				Domain:                 "full.example.com",
				Type:                   "self_hosted",
				SessionDuration:        "24h",
				AutoRedirectToIdentity: true,
				EnableBindingCookie:    true,
				CustomDenyMessage:      "Access denied",
				CustomDenyURL:          "https://example.com/denied",
				CORSHeaders: &CORSHeaders{
					AllowedOrigins: []string{"https://example.com"},
				},
			},
		},
		{
			name: "nil cors headers omitted",
			config: ApplicationConfig{
				Name: "No CORS App",
				Type: "self_hosted",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.config)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got ApplicationConfig
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.config, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.config, got)
			}
		})
	}
}

// TestApplicationConfigCORSNilOmitted verifies that CORSHeaders=nil is
// omitted from JSON output.
func TestApplicationConfigCORSNilOmitted(t *testing.T) {
	config := ApplicationConfig{Name: "App", Type: "self_hosted"}
	data, err := json.Marshal(config)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}
	if _, ok := raw["corsHeaders"]; ok {
		t.Error("expected 'corsHeaders' to be omitted when nil")
	}
}

// --- CloudflareAccessPolicySpec ---

// TestCloudflareAccessPolicySpecJSONRoundTrip verifies the full spec
// serializes and deserializes correctly.
func TestCloudflareAccessPolicySpecJSONRoundTrip(t *testing.T) {
	defaultNS := gatewayv1.Namespace("default")
	tests := []struct {
		name string
		spec CloudflareAccessPolicySpec
	}{
		{
			name: "minimal spec httproute target",
			spec: CloudflareAccessPolicySpec{
				TargetRef: PolicyTargetReference{
					Group: "gateway.networking.k8s.io",
					Kind:  "HTTPRoute",
					Name:  "my-route",
				},
				Policies: []AccessPolicy{
					{
						Decision: "allow",
						Rules: []AccessPolicyRule{
							{Emails: []string{"user@example.com"}},
						},
					},
				},
			},
		},
		{
			name: "spec with gateway target and namespace",
			spec: CloudflareAccessPolicySpec{
				TargetRef: PolicyTargetReference{
					Group:     "gateway.networking.k8s.io",
					Kind:      "Gateway",
					Name:      "my-gateway",
					Namespace: &defaultNS,
				},
				Policies: []AccessPolicy{
					{
						Name:     "allow-all",
						Decision: "allow",
						Rules:    []AccessPolicyRule{{Everyone: true}},
					},
				},
			},
		},
		{
			name: "spec with application config",
			spec: CloudflareAccessPolicySpec{
				TargetRef: PolicyTargetReference{
					Group: "gateway.networking.k8s.io",
					Kind:  "HTTPRoute",
					Name:  "my-route",
				},
				Application: ApplicationConfig{
					Name:            "My App",
					SessionDuration: "24h",
					Type:            "self_hosted",
				},
				Policies: []AccessPolicy{
					{
						Decision: "deny",
						Rules:    []AccessPolicyRule{{Countries: []string{"CN", "RU"}}},
					},
				},
			},
		},
		{
			name: "spec with external policy id",
			spec: CloudflareAccessPolicySpec{
				TargetRef: PolicyTargetReference{
					Group: "gateway.networking.k8s.io",
					Kind:  "HTTPRoute",
					Name:  "my-route",
				},
				Policies: []AccessPolicy{
					{ExternalPolicyID: "existing-policy-id-123"},
				},
			},
		},
		{
			name: "spec with multiple policies",
			spec: CloudflareAccessPolicySpec{
				TargetRef: PolicyTargetReference{
					Group: "gateway.networking.k8s.io",
					Kind:  "HTTPRoute",
					Name:  "my-route",
				},
				Policies: []AccessPolicy{
					{
						Name:     "deny-countries",
						Decision: "deny",
						Rules:    []AccessPolicyRule{{Countries: []string{"XX"}}},
					},
					{
						Name:     "allow-employees",
						Decision: "allow",
						Rules:    []AccessPolicyRule{{EmailDomains: []string{"example.com"}}},
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.spec)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CloudflareAccessPolicySpec
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.spec, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.spec, got)
			}
		})
	}
}

// TestPolicyTargetReferenceNamespaceOmitted verifies that Namespace=nil is
// omitted from the target reference JSON output.
func TestPolicyTargetReferenceNamespaceOmitted(t *testing.T) {
	ref := PolicyTargetReference{
		Group: "gateway.networking.k8s.io",
		Kind:  "HTTPRoute",
		Name:  "my-route",
	}
	data, err := json.Marshal(ref)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}
	if _, ok := raw["namespace"]; ok {
		t.Error("expected 'namespace' to be omitted when nil")
	}
}

// --- CloudflareAccessPolicyStatus ---

// TestCloudflareAccessPolicyStatusJSONRoundTrip verifies the status
// serializes and deserializes correctly.
func TestCloudflareAccessPolicyStatusJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name   string
		status CloudflareAccessPolicyStatus
	}{
		{
			name:   "empty status",
			status: CloudflareAccessPolicyStatus{},
		},
		{
			name: "status with application id",
			status: CloudflareAccessPolicyStatus{
				ApplicationID: "app-123-abc",
				TargetDomain:  "app.example.com",
			},
		},
		{
			name: "status with policy ids and generation",
			status: CloudflareAccessPolicyStatus{
				ApplicationID:      "app-123-abc",
				PolicyIDs:          []string{"policy-1", "policy-2"},
				TargetDomain:       "app.example.com",
				ObservedGeneration: 5,
			},
		},
		{
			name: "status with conditions",
			status: CloudflareAccessPolicyStatus{
				ApplicationID: "app-xyz",
				TargetDomain:  "test.example.com",
				Conditions: []metav1.Condition{
					{
						Type:               TypeAccepted,
						Status:             metav1.ConditionTrue,
						Reason:             ReasonAccepted,
						Message:            "policy accepted",
						LastTransitionTime: fixedTime,
					},
					{
						Type:               TypeProgrammed,
						Status:             metav1.ConditionTrue,
						Reason:             ReasonProgrammed,
						Message:            "policy programmed in Cloudflare",
						LastTransitionTime: fixedTime,
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.status)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CloudflareAccessPolicyStatus
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			// Use JSON byte comparison instead of reflect.DeepEqual to avoid
			// spurious failures caused by metav1.Time.UnmarshalJSON calling
			// pt.Local(), which produces a different *time.Location pointer
			// than time.UTC even when both represent UTC.
			gotData, err := json.Marshal(got)
			if err != nil {
				t.Fatalf("re-Marshal() error = %v", err)
			}
			if !bytes.Equal(data, gotData) {
				t.Errorf("round-trip mismatch:\n  want: %s\n  got:  %s", data, gotData)
			}
		})
	}
}

// TestCloudflareAccessPolicyStatusJSONFieldNames verifies the JSON field name
// for ApplicationID uses camelCase "applicationId" as documented.
func TestCloudflareAccessPolicyStatusJSONFieldNames(t *testing.T) {
	status := CloudflareAccessPolicyStatus{
		ApplicationID: "app-123",
		PolicyIDs:     []string{"pol-1"},
		TargetDomain:  "app.example.com",
	}
	data, err := json.Marshal(status)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal error = %v", err)
	}

	expectedKeys := []string{"applicationId", "policyIds", "targetDomain"}
	for _, key := range expectedKeys {
		t.Run(key, func(t *testing.T) {
			if _, ok := raw[key]; !ok {
				t.Errorf("expected JSON key %q to be present in status", key)
			}
		})
	}
}

// --- Access Policy Condition Constants ---

// TestAccessPolicyConditionTypeValues verifies condition type constants
// defined in cloudflareaccesspolicy_types.go have correct values.
func TestAccessPolicyConditionTypeValues(t *testing.T) {
	tests := []struct {
		name string
		got  string
		want string
	}{
		{"TypeAccepted", TypeAccepted, "Accepted"},
		{"TypeResolvedRefs", TypeResolvedRefs, "ResolvedRefs"},
		{"TypeProgrammed", TypeProgrammed, "Programmed"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Errorf("%s = %q, want %q", tt.name, tt.got, tt.want)
			}
		})
	}
}

// TestAccessPolicyConditionReasonValues verifies condition reason constants
// defined in cloudflareaccesspolicy_types.go have correct values.
func TestAccessPolicyConditionReasonValues(t *testing.T) {
	tests := []struct {
		name string
		got  string
		want string
	}{
		{"ReasonAccepted", ReasonAccepted, "Accepted"},
		{"ReasonInvalid", ReasonInvalid, "Invalid"},
		{"ReasonRefNotPermitted", ReasonRefNotPermitted, "RefNotPermitted"},
		{"ReasonProgrammed", ReasonProgrammed, "Programmed"},
		{"ReasonCloudflareError", ReasonCloudflareError, "CloudflareError"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Errorf("%s = %q, want %q", tt.name, tt.got, tt.want)
			}
		})
	}
}

// TestAccessPolicyConditionTypeNonEmpty verifies that no access policy
// condition type constant is empty.
func TestAccessPolicyConditionTypeNonEmpty(t *testing.T) {
	types := []struct {
		name  string
		value string
	}{
		{"TypeAccepted", TypeAccepted},
		{"TypeResolvedRefs", TypeResolvedRefs},
		{"TypeProgrammed", TypeProgrammed},
	}
	for _, tt := range types {
		t.Run(tt.name, func(t *testing.T) {
			if tt.value == "" {
				t.Errorf("%s must not be empty", tt.name)
			}
		})
	}
}

// TestAccessPolicyConditionTypeUniqueness verifies all access policy condition
// type constants are distinct from each other.
func TestAccessPolicyConditionTypeUniqueness(t *testing.T) {
	types := map[string]string{
		"TypeAccepted":     TypeAccepted,
		"TypeResolvedRefs": TypeResolvedRefs,
		"TypeProgrammed":   TypeProgrammed,
	}
	seen := make(map[string]string)
	for constName, value := range types {
		if existing, dup := seen[value]; dup {
			t.Errorf("duplicate condition type value %q: both %s and %s", value, existing, constName)
		}
		seen[value] = constName
	}
}

// --- Scheme Registration ---

// TestSchemeRegistration verifies that the init() functions in both type files
// correctly register all CRD types so that AddToScheme populates a
// runtime.Scheme with the expected types.
func TestSchemeRegistration(t *testing.T) {
	s := runtime.NewScheme()
	if err := AddToScheme(s); err != nil {
		t.Fatalf("AddToScheme() error = %v", err)
	}

	types := []struct {
		name string
		obj  runtime.Object
	}{
		{"CloudflareTunnel", &CloudflareTunnel{}},
		{"CloudflareTunnelList", &CloudflareTunnelList{}},
		{"CloudflareAccessPolicy", &CloudflareAccessPolicy{}},
		{"CloudflareAccessPolicyList", &CloudflareAccessPolicyList{}},
	}

	for _, tt := range types {
		t.Run(tt.name, func(t *testing.T) {
			gvks, _, err := s.ObjectKinds(tt.obj)
			if err != nil {
				t.Fatalf("%s not registered in scheme: %v", tt.name, err)
			}
			if len(gvks) == 0 {
				t.Errorf("%s has no GVKs registered", tt.name)
				return
			}
			// All types must be under the Cloudflare operator group/version
			for _, gvk := range gvks {
				if gvk.Group != GroupVersion.Group {
					t.Errorf("%s: expected group %q, got %q", tt.name, GroupVersion.Group, gvk.Group)
				}
				if gvk.Version != GroupVersion.Version {
					t.Errorf("%s: expected version %q, got %q", tt.name, GroupVersion.Version, gvk.Version)
				}
			}
		})
	}
}

// TestGroupVersionValues verifies the GroupVersion is set to the correct
// Cloudflare operator API group and version.
func TestGroupVersionValues(t *testing.T) {
	if GroupVersion.Group != "tunnels.cloudflare.io" {
		t.Errorf("GroupVersion.Group = %q, want %q", GroupVersion.Group, "tunnels.cloudflare.io")
	}
	if GroupVersion.Version != "v1" {
		t.Errorf("GroupVersion.Version = %q, want %q", GroupVersion.Version, "v1")
	}
}

// --- Full resource round-trips ---

// TestCloudflareTunnelJSONRoundTrip verifies the full CloudflareTunnel
// resource serializes and deserializes correctly including TypeMeta and
// ObjectMeta.
func TestCloudflareTunnelJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name   string
		tunnel CloudflareTunnel
	}{
		{
			name: "minimal tunnel",
			tunnel: CloudflareTunnel{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "tunnels.cloudflare.io/v1",
					Kind:       "CloudflareTunnel",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name:      "my-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					Name:      "my-tunnel",
					AccountID: "account-abc-123",
				},
			},
		},
		{
			name: "tunnel with full spec and status",
			tunnel: CloudflareTunnel{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "tunnels.cloudflare.io/v1",
					Kind:       "CloudflareTunnel",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name:            "full-tunnel",
					Namespace:       "production",
					ResourceVersion: "12345",
				},
				Spec: CloudflareTunnelSpec{
					Name:         "full-tunnel",
					AccountID:    "account-xyz-456",
					ConfigSource: "cloudflare",
					Ingress: []TunnelIngress{
						{Hostname: "app.example.com", Service: "http://app:8080"},
						{Service: "http_status:404"},
					},
				},
				Status: CloudflareTunnelStatus{
					Phase:    "Ready",
					TunnelID: "tunnel-abc-789",
					Active:   true,
					Ready:    true,
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.tunnel)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CloudflareTunnel
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.tunnel, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.tunnel, got)
			}
		})
	}
}

// TestCloudflareAccessPolicyJSONRoundTrip verifies the full
// CloudflareAccessPolicy resource serializes and deserializes correctly.
func TestCloudflareAccessPolicyJSONRoundTrip(t *testing.T) {
	productionNS := gatewayv1.Namespace("production")
	tests := []struct {
		name   string
		policy CloudflareAccessPolicy
	}{
		{
			name: "minimal policy",
			policy: CloudflareAccessPolicy{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "tunnels.cloudflare.io/v1",
					Kind:       "CloudflareAccessPolicy",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name:      "my-policy",
					Namespace: "default",
				},
				Spec: CloudflareAccessPolicySpec{
					TargetRef: PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  "my-route",
					},
					Policies: []AccessPolicy{
						{
							Decision: "allow",
							Rules:    []AccessPolicyRule{{Emails: []string{"user@example.com"}}},
						},
					},
				},
			},
		},
		{
			name: "policy with namespace and application config",
			policy: CloudflareAccessPolicy{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "tunnels.cloudflare.io/v1",
					Kind:       "CloudflareAccessPolicy",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name:            "full-policy",
					Namespace:       "production",
					ResourceVersion: "99",
				},
				Spec: CloudflareAccessPolicySpec{
					TargetRef: PolicyTargetReference{
						Group:     "gateway.networking.k8s.io",
						Kind:      "Gateway",
						Name:      "main-gateway",
						Namespace: &productionNS,
					},
					Application: ApplicationConfig{
						Name:            "Production App",
						SessionDuration: "24h",
						Type:            "self_hosted",
					},
					Policies: []AccessPolicy{
						{
							Name:     "employee-access",
							Decision: "allow",
							Rules: []AccessPolicyRule{
								{EmailDomains: []string{"company.com"}},
							},
						},
					},
				},
				Status: CloudflareAccessPolicyStatus{
					ApplicationID: "cf-app-123",
					PolicyIDs:     []string{"cf-pol-456"},
					TargetDomain:  "app.example.com",
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.policy)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got CloudflareAccessPolicy
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.policy, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.policy, got)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// DeepCopy nil-receiver tests
// ---------------------------------------------------------------------------

func TestDeepCopyNilReceivers(t *testing.T) {
	t.Run("AccessPolicy nil", func(t *testing.T) {
		if got := (*AccessPolicy)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("AccessPolicyRule nil", func(t *testing.T) {
		if got := (*AccessPolicyRule)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("ApplicationConfig nil", func(t *testing.T) {
		if got := (*ApplicationConfig)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CORSHeaders nil", func(t *testing.T) {
		if got := (*CORSHeaders)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareAccessPolicy nil", func(t *testing.T) {
		if got := (*CloudflareAccessPolicy)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareAccessPolicyList nil", func(t *testing.T) {
		if got := (*CloudflareAccessPolicyList)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareAccessPolicySpec nil", func(t *testing.T) {
		if got := (*CloudflareAccessPolicySpec)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareAccessPolicyStatus nil", func(t *testing.T) {
		if got := (*CloudflareAccessPolicyStatus)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareTunnel nil", func(t *testing.T) {
		if got := (*CloudflareTunnel)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareTunnelList nil", func(t *testing.T) {
		if got := (*CloudflareTunnelList)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareTunnelSpec nil", func(t *testing.T) {
		if got := (*CloudflareTunnelSpec)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("CloudflareTunnelStatus nil", func(t *testing.T) {
		if got := (*CloudflareTunnelStatus)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("PolicyTargetReference nil", func(t *testing.T) {
		if got := (*PolicyTargetReference)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("SecretReference nil", func(t *testing.T) {
		if got := (*SecretReference)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
	t.Run("TunnelIngress nil", func(t *testing.T) {
		if got := (*TunnelIngress)(nil).DeepCopy(); got != nil {
			t.Errorf("expected nil, got %v", got)
		}
	})
}

// ---------------------------------------------------------------------------
// DeepCopy mutation-isolation tests
// ---------------------------------------------------------------------------

func TestAccessPolicyRuleDeepCopy(t *testing.T) {
	orig := &AccessPolicyRule{
		EmailsEndingIn:      []string{"@acme.com"},
		Emails:              []string{"alice@acme.com"},
		EmailDomains:        []string{"acme.com"},
		IPRanges:            []string{"10.0.0.0/8"},
		GitHubUsers:         []string{"alice"},
		GitHubOrganizations: []string{"acme-org"},
		Countries:           []string{"US"},
	}
	cp := orig.DeepCopy()
	cp.EmailsEndingIn[0] = "mutated"
	cp.Emails[0] = "mutated"
	cp.EmailDomains[0] = "mutated"
	cp.IPRanges[0] = "mutated"
	cp.GitHubUsers[0] = "mutated"
	cp.GitHubOrganizations[0] = "mutated"
	cp.Countries[0] = "mutated"
	if orig.EmailsEndingIn[0] != "@acme.com" {
		t.Errorf("EmailsEndingIn mutated original")
	}
	if orig.Emails[0] != "alice@acme.com" {
		t.Errorf("Emails mutated original")
	}
	if orig.EmailDomains[0] != "acme.com" {
		t.Errorf("EmailDomains mutated original")
	}
	if orig.IPRanges[0] != "10.0.0.0/8" {
		t.Errorf("IPRanges mutated original")
	}
	if orig.GitHubUsers[0] != "alice" {
		t.Errorf("GitHubUsers mutated original")
	}
	if orig.GitHubOrganizations[0] != "acme-org" {
		t.Errorf("GitHubOrganizations mutated original")
	}
	if orig.Countries[0] != "US" {
		t.Errorf("Countries mutated original")
	}
}

func TestAccessPolicyDeepCopy(t *testing.T) {
	orig := &AccessPolicy{
		Rules: []AccessPolicyRule{
			{Emails: []string{"alice@acme.com"}},
		},
	}
	cp := orig.DeepCopy()
	cp.Rules[0].Emails[0] = "mutated"
	if orig.Rules[0].Emails[0] != "alice@acme.com" {
		t.Errorf("Rules mutated original")
	}
}

func TestCORSHeadersDeepCopy(t *testing.T) {
	maxAge := 3600
	orig := &CORSHeaders{
		AllowedOrigins: []string{"https://example.com"},
		AllowedMethods: []string{"GET", "POST"},
		AllowedHeaders: []string{"Authorization"},
		MaxAge:         &maxAge,
	}
	cp := orig.DeepCopy()
	cp.AllowedOrigins[0] = "mutated"
	cp.AllowedMethods[0] = "mutated"
	cp.AllowedHeaders[0] = "mutated"
	*cp.MaxAge = 9999
	if orig.AllowedOrigins[0] != "https://example.com" {
		t.Errorf("AllowedOrigins mutated original")
	}
	if orig.AllowedMethods[0] != "GET" {
		t.Errorf("AllowedMethods mutated original")
	}
	if orig.AllowedHeaders[0] != "Authorization" {
		t.Errorf("AllowedHeaders mutated original")
	}
	if *orig.MaxAge != 3600 {
		t.Errorf("MaxAge mutated original")
	}
}

func TestApplicationConfigDeepCopy(t *testing.T) {
	maxAge := 600
	orig := &ApplicationConfig{
		CORSHeaders: &CORSHeaders{
			AllowedOrigins: []string{"https://app.example.com"},
			MaxAge:         &maxAge,
		},
	}
	cp := orig.DeepCopy()
	cp.CORSHeaders.AllowedOrigins[0] = "mutated"
	*cp.CORSHeaders.MaxAge = 9999
	if orig.CORSHeaders.AllowedOrigins[0] != "https://app.example.com" {
		t.Errorf("CORSHeaders.AllowedOrigins mutated original")
	}
	if *orig.CORSHeaders.MaxAge != 600 {
		t.Errorf("CORSHeaders.MaxAge mutated original")
	}
}

func TestPolicyTargetReferenceDeepCopy(t *testing.T) {
	ns := gatewayv1.Namespace("default")
	orig := &PolicyTargetReference{
		Namespace: &ns,
	}
	cp := orig.DeepCopy()
	newNs := gatewayv1.Namespace("other")
	cp.Namespace = &newNs
	if *orig.Namespace != "default" {
		t.Errorf("Namespace mutated original")
	}
}

func TestCloudflareAccessPolicyStatusDeepCopy(t *testing.T) {
	orig := &CloudflareAccessPolicyStatus{
		PolicyIDs: []string{"pol-1", "pol-2"},
	}
	cp := orig.DeepCopy()
	cp.PolicyIDs[0] = "mutated"
	if orig.PolicyIDs[0] != "pol-1" {
		t.Errorf("PolicyIDs mutated original")
	}
}

func TestCloudflareAccessPolicySpecDeepCopy(t *testing.T) {
	orig := &CloudflareAccessPolicySpec{
		Policies: []AccessPolicy{
			{Rules: []AccessPolicyRule{{Emails: []string{"alice@acme.com"}}}},
		},
	}
	cp := orig.DeepCopy()
	cp.Policies[0].Rules[0].Emails[0] = "mutated"
	if orig.Policies[0].Rules[0].Emails[0] != "alice@acme.com" {
		t.Errorf("Policies mutated original")
	}
}

func TestCloudflareAccessPolicyListDeepCopy(t *testing.T) {
	orig := &CloudflareAccessPolicyList{
		Items: []CloudflareAccessPolicy{
			{
				Spec: CloudflareAccessPolicySpec{
					Policies: []AccessPolicy{
						{Rules: []AccessPolicyRule{{Emails: []string{"alice@acme.com"}}}},
					},
				},
			},
		},
	}
	cp := orig.DeepCopy()
	cp.Items[0].Spec.Policies[0].Rules[0].Emails[0] = "mutated"
	if orig.Items[0].Spec.Policies[0].Rules[0].Emails[0] != "alice@acme.com" {
		t.Errorf("Items mutated original")
	}
}

func TestCloudflareTunnelSpecDeepCopy(t *testing.T) {
	orig := &CloudflareTunnelSpec{
		AccountID: "acct-1",
		Ingress: []TunnelIngress{
			{Hostname: "app.example.com", Service: "http://backend:8080"},
		},
	}
	cp := orig.DeepCopy()
	cp.Ingress[0].Hostname = "mutated"
	if orig.Ingress[0].Hostname != "app.example.com" {
		t.Errorf("Ingress mutated original")
	}
}

func TestCloudflareTunnelStatusDeepCopy(t *testing.T) {
	orig := &CloudflareTunnelStatus{
		Conditions: []metav1.Condition{
			{Type: "Ready", Status: metav1.ConditionTrue, Reason: "Running"},
		},
	}
	cp := orig.DeepCopy()
	cp.Conditions[0].Type = "mutated"
	if orig.Conditions[0].Type != "Ready" {
		t.Errorf("Conditions mutated original")
	}
}

func TestCloudflareTunnelListDeepCopy(t *testing.T) {
	orig := &CloudflareTunnelList{
		Items: []CloudflareTunnel{
			{
				Spec: CloudflareTunnelSpec{
					AccountID: "acct-1",
					Ingress: []TunnelIngress{
						{Hostname: "app.example.com", Service: "http://backend:8080"},
					},
				},
			},
		},
	}
	cp := orig.DeepCopy()
	cp.Items[0].Spec.Ingress[0].Hostname = "mutated"
	if orig.Items[0].Spec.Ingress[0].Hostname != "app.example.com" {
		t.Errorf("Items.Spec.Ingress mutated original")
	}
}

// ---------------------------------------------------------------------------
// DeepCopyObject tests
// ---------------------------------------------------------------------------

func TestDeepCopyObject(t *testing.T) {
	t.Run("CloudflareTunnel", func(t *testing.T) {
		orig := &CloudflareTunnel{
			Spec: CloudflareTunnelSpec{
				AccountID: "acct-1",
				Ingress:   []TunnelIngress{{Hostname: "a.example.com", Service: "http://svc:8080"}},
			},
		}
		obj := orig.DeepCopyObject()
		if obj == nil {
			t.Fatal("expected non-nil")
		}
		cp, ok := obj.(*CloudflareTunnel)
		if !ok {
			t.Fatalf("expected *CloudflareTunnel, got %T", obj)
		}
		cp.Spec.Ingress[0].Hostname = "mutated"
		if orig.Spec.Ingress[0].Hostname != "a.example.com" {
			t.Errorf("DeepCopyObject mutated original")
		}
	})

	t.Run("CloudflareTunnel nil", func(t *testing.T) {
		var orig *CloudflareTunnel
		if obj := orig.DeepCopyObject(); obj != nil {
			t.Errorf("expected nil, got %v", obj)
		}
	})

	t.Run("CloudflareTunnelList", func(t *testing.T) {
		orig := &CloudflareTunnelList{
			Items: []CloudflareTunnel{
				{Spec: CloudflareTunnelSpec{AccountID: "acct-1"}},
			},
		}
		obj := orig.DeepCopyObject()
		if obj == nil {
			t.Fatal("expected non-nil")
		}
		if _, ok := obj.(*CloudflareTunnelList); !ok {
			t.Fatalf("expected *CloudflareTunnelList, got %T", obj)
		}
	})

	t.Run("CloudflareTunnelList nil", func(t *testing.T) {
		var orig *CloudflareTunnelList
		if obj := orig.DeepCopyObject(); obj != nil {
			t.Errorf("expected nil, got %v", obj)
		}
	})

	t.Run("CloudflareAccessPolicy", func(t *testing.T) {
		orig := &CloudflareAccessPolicy{
			Spec: CloudflareAccessPolicySpec{
				Policies: []AccessPolicy{
					{Rules: []AccessPolicyRule{{Emails: []string{"alice@acme.com"}}}},
				},
			},
		}
		obj := orig.DeepCopyObject()
		if obj == nil {
			t.Fatal("expected non-nil")
		}
		cp, ok := obj.(*CloudflareAccessPolicy)
		if !ok {
			t.Fatalf("expected *CloudflareAccessPolicy, got %T", obj)
		}
		cp.Spec.Policies[0].Rules[0].Emails[0] = "mutated"
		if orig.Spec.Policies[0].Rules[0].Emails[0] != "alice@acme.com" {
			t.Errorf("DeepCopyObject mutated original")
		}
	})

	t.Run("CloudflareAccessPolicy nil", func(t *testing.T) {
		var orig *CloudflareAccessPolicy
		if obj := orig.DeepCopyObject(); obj != nil {
			t.Errorf("expected nil, got %v", obj)
		}
	})

	t.Run("CloudflareAccessPolicyList", func(t *testing.T) {
		orig := &CloudflareAccessPolicyList{
			Items: []CloudflareAccessPolicy{
				{Spec: CloudflareAccessPolicySpec{Policies: []AccessPolicy{{Rules: []AccessPolicyRule{{Emails: []string{"alice@acme.com"}}}}}}},
			},
		}
		obj := orig.DeepCopyObject()
		if obj == nil {
			t.Fatal("expected non-nil")
		}
		if _, ok := obj.(*CloudflareAccessPolicyList); !ok {
			t.Fatalf("expected *CloudflareAccessPolicyList, got %T", obj)
		}
	})

	t.Run("CloudflareAccessPolicyList nil", func(t *testing.T) {
		var orig *CloudflareAccessPolicyList
		if obj := orig.DeepCopyObject(); obj != nil {
			t.Errorf("expected nil, got %v", obj)
		}
	})
}

// ---------------------------------------------------------------------------
// ValidateUpdate type-assertion error paths
// ---------------------------------------------------------------------------

func TestValidateUpdateTypeAssertionErrors(t *testing.T) {
	ctx := context.Background()
	r := &CloudflareTunnel{
		Spec: CloudflareTunnelSpec{AccountID: "acct-1"},
	}

	t.Run("newObj wrong type", func(t *testing.T) {
		wrongType := &CloudflareAccessPolicy{}
		_, err := r.ValidateUpdate(ctx, r, wrongType)
		if err == nil {
			t.Fatal("expected error, got nil")
		}
		if !strings.Contains(err.Error(), "new object is not a CloudflareTunnel") {
			t.Errorf("unexpected error message: %v", err)
		}
	})

	t.Run("oldObj wrong type", func(t *testing.T) {
		wrongType := &CloudflareAccessPolicy{}
		validNew := &CloudflareTunnel{
			Spec: CloudflareTunnelSpec{AccountID: "acct-1"},
		}
		_, err := r.ValidateUpdate(ctx, wrongType, validNew)
		if err == nil {
			t.Fatal("expected error, got nil")
		}
		if !strings.Contains(err.Error(), "old object is not a CloudflareTunnel") {
			t.Errorf("unexpected error message: %v", err)
		}
	})
}

// ---------------------------------------------------------------------------
// ValidateDelete
// ---------------------------------------------------------------------------

func TestValidateDelete(t *testing.T) {
	ctx := context.Background()
	r := &CloudflareTunnel{
		Spec: CloudflareTunnelSpec{AccountID: "acct-1"},
	}
	warnings, err := r.ValidateDelete(ctx, r)
	if err != nil {
		t.Errorf("ValidateDelete() returned unexpected error: %v", err)
	}
	if warnings != nil {
		t.Errorf("ValidateDelete() returned unexpected warnings: %v", warnings)
	}
}

// ---------------------------------------------------------------------------
// isValidHostname edge cases
// ---------------------------------------------------------------------------

func TestIsValidHostnameEdgeCases(t *testing.T) {
	// 63-char label: valid (max allowed label length)
	label63 := strings.Repeat("a", 63)
	// 64-char label: invalid (exceeds max label length)
	label64 := strings.Repeat("a", 64)

	// Build a 253-char hostname across 4 labels: 63+1+62+1+63+1+62 = 253.
	hostname253 := strings.Repeat("a", 63) + "." + strings.Repeat("b", 62) + "." + strings.Repeat("c", 63) + "." + strings.Repeat("d", 62)
	// 254-char hostname: append one extra character.
	hostname254 := strings.Repeat("a", 63) + "." + strings.Repeat("b", 62) + "." + strings.Repeat("c", 63) + "." + strings.Repeat("d", 63)

	tests := []struct {
		name     string
		hostname string
		want     bool
	}{
		{
			name:     "exactly 63-char label is valid",
			hostname: label63 + ".example.com",
			want:     true,
		},
		{
			name:     "exactly 64-char label is invalid",
			hostname: label64 + ".example.com",
			want:     false,
		},
		{
			name:     "exactly 253-char hostname is valid",
			hostname: hostname253,
			want:     true,
		},
		{
			name:     "254-char hostname is invalid",
			hostname: hostname254,
			want:     false,
		},
		{
			name:     "wildcard prefix is invalid",
			hostname: "*.example.com",
			want:     false,
		},
		{
			name:     "single-char label is valid",
			hostname: "a.example.com",
			want:     true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isValidHostname(tt.hostname); got != tt.want {
				t.Errorf("isValidHostname(%q) = %v, want %v (len=%d)", tt.hostname, got, tt.want, len(tt.hostname))
			}
		})
	}
}
