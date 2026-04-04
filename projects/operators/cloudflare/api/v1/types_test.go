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
	"encoding/json"
	"reflect"
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
			if !reflect.DeepEqual(tt.status, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.status, got)
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
			if !reflect.DeepEqual(tt.status, got) {
				t.Errorf("round-trip mismatch:\n  want: %+v\n  got:  %+v", tt.status, got)
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
