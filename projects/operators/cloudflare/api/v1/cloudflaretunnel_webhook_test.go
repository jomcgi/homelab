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
	"context"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestCloudflareTunnelValidateCreate(t *testing.T) {
	tests := []struct {
		name    string
		tunnel  *CloudflareTunnel
		wantErr bool
		errMsg  string
	}{
		{
			name: "valid tunnel with accountID",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Name:      "test-tunnel",
				},
			},
			wantErr: false,
		},
		{
			name: "missing accountID should fail",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					Name: "test-tunnel",
				},
			},
			wantErr: true,
			errMsg:  "accountID is required",
		},
		{
			name: "valid ingress with hostname and service",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "example.com",
							Service:  "http://backend:8080",
						},
					},
				},
			},
			wantErr: false,
		},
		{
			name: "invalid hostname should fail",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "invalid_hostname!@#",
							Service:  "http://backend:8080",
						},
					},
				},
			},
			wantErr: true,
			errMsg:  "must be a valid hostname",
		},
		{
			name: "missing service should fail",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "example.com",
							Service:  "",
						},
					},
				},
			},
			wantErr: true,
			errMsg:  "service is required",
		},
		{
			name: "invalid service URL should fail",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "example.com",
							Service:  "invalid-service",
						},
					},
				},
			},
			wantErr: true,
			errMsg:  "service must be a valid URL",
		},
		{
			name: "valid http_status service",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "",
							Service:  "http_status:404",
						},
					},
				},
			},
			wantErr: false,
		},
		{
			name: "valid hello_world service",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "test.example.com",
							Service:  "hello_world",
						},
					},
				},
			},
			wantErr: false,
		},
		{
			name: "multiple catch-all rules should fail",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "",
							Service:  "http_status:404",
						},
						{
							Hostname: "",
							Service:  "http_status:503",
						},
					},
				},
			},
			wantErr: true,
			errMsg:  "only one catch-all rule",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := tt.tunnel.ValidateCreate(context.Background(), tt.tunnel)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateCreate() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr && err != nil {
				if tt.errMsg != "" && !contains(err.Error(), tt.errMsg) {
					t.Errorf("ValidateCreate() error = %v, expected to contain %q", err, tt.errMsg)
				}
			}
		})
	}
}

func TestCloudflareTunnelValidateUpdate(t *testing.T) {
	tests := []struct {
		name      string
		oldTunnel *CloudflareTunnel
		newTunnel *CloudflareTunnel
		wantErr   bool
		errMsg    string
	}{
		{
			name: "valid update without accountID change",
			oldTunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Name:      "test-tunnel",
				},
			},
			newTunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Name:      "test-tunnel-updated",
				},
			},
			wantErr: false,
		},
		{
			name: "changing accountID should fail",
			oldTunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Name:      "test-tunnel",
				},
			},
			newTunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "different-account-456",
					Name:      "test-tunnel",
				},
			},
			wantErr: true,
			errMsg:  "accountID is immutable",
		},
		{
			name: "updating ingress rules is allowed",
			oldTunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "old.example.com",
							Service:  "http://backend:8080",
						},
					},
				},
			},
			newTunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "test-account-123",
					Ingress: []TunnelIngress{
						{
							Hostname: "new.example.com",
							Service:  "http://backend:9090",
						},
					},
				},
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := tt.newTunnel.ValidateUpdate(context.Background(), tt.oldTunnel, tt.newTunnel)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateUpdate() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if tt.wantErr && err != nil {
				if tt.errMsg != "" && !contains(err.Error(), tt.errMsg) {
					t.Errorf("ValidateUpdate() error = %v, expected to contain %q", err, tt.errMsg)
				}
			}
		})
	}
}

func TestIsValidHostname(t *testing.T) {
	tests := []struct {
		name     string
		hostname string
		want     bool
	}{
		{"valid simple hostname", "example.com", true},
		{"valid subdomain", "sub.example.com", true},
		{"valid multiple subdomains", "a.b.c.example.com", true},
		{"valid with hyphen", "my-service.example.com", true},
		{"invalid underscore", "my_service.example.com", false},
		{"invalid starts with hyphen", "-example.com", false},
		{"invalid ends with hyphen", "example-.com", false},
		{"invalid special chars", "example!.com", false},
		{"invalid empty", "", false},
		{"invalid too long", string(make([]byte, 254)), false},
		{"valid single label", "localhost", true},
		{"invalid space", "example .com", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isValidHostname(tt.hostname); got != tt.want {
				t.Errorf("isValidHostname(%q) = %v, want %v", tt.hostname, got, tt.want)
			}
		})
	}
}

func TestValidateServiceURL(t *testing.T) {
	tests := []struct {
		name    string
		service string
		wantErr bool
	}{
		{"valid http", "http://backend:8080", false},
		{"valid https", "https://backend:443", false},
		{"valid unix socket", "unix:///tmp/socket", false},
		{"valid tcp", "tcp://localhost:3306", false},
		{"valid ssh", "ssh://server:22", false},
		{"valid rdp", "rdp://server:3389", false},
		{"valid smb", "smb://server/share", false},
		{"valid http_status", "http_status:404", false},
		{"valid hello_world", "hello_world", false},
		{"valid hello-world", "hello-world", false},
		{"invalid random string", "invalid-service", true},
		{"invalid no protocol", "backend:8080", true},
		{"invalid ftp", "ftp://server", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateServiceURL(tt.service)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateServiceURL(%q) error = %v, wantErr %v", tt.service, err, tt.wantErr)
			}
		})
	}
}

// Helper function to check if a string contains a substring
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
		(len(s) > 0 && len(substr) > 0 && stringContains(s, substr)))
}

func stringContains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
