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
	"k8s.io/apimachinery/pkg/runtime"
)

// TestCloudflareTunnelValidateDelete checks that ValidateDelete always
// succeeds (no validation needed on deletion).
func TestCloudflareTunnelValidateDelete(t *testing.T) {
	tests := []struct {
		name    string
		tunnel  *CloudflareTunnel
		wantErr bool
	}{
		{
			name: "delete valid tunnel with all fields set",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{
					AccountID: "account-123",
					Name:      "test-tunnel",
					Ingress: []TunnelIngress{
						{
							Hostname: "app.example.com",
							Service:  "http://backend:8080",
						},
					},
				},
			},
			wantErr: false,
		},
		{
			name: "delete tunnel missing accountID still succeeds",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "no-account-tunnel",
					Namespace: "default",
				},
				Spec: CloudflareTunnelSpec{},
			},
			wantErr: false,
		},
		{
			name: "delete minimal tunnel with no spec",
			tunnel: &CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "empty-tunnel",
					Namespace: "default",
				},
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := tt.tunnel.ValidateDelete(context.Background(), tt.tunnel)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateDelete() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

// TestCloudflareTunnelValidateUpdateTypeErrors checks the error paths where
// the runtime.Object parameters are not *CloudflareTunnel instances.
func TestCloudflareTunnelValidateUpdateTypeErrors(t *testing.T) {
	validTunnel := &CloudflareTunnel{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-tunnel",
			Namespace: "default",
		},
		Spec: CloudflareTunnelSpec{
			AccountID: "account-123",
			Name:      "test-tunnel",
		},
	}

	t.Run("newObj is not a CloudflareTunnel returns error", func(t *testing.T) {
		badObj := &wrongType{}
		_, err := validTunnel.ValidateUpdate(context.Background(), validTunnel, badObj)
		if err == nil {
			t.Errorf("ValidateUpdate() expected error when newObj is wrong type, got nil")
		}
		if !contains(err.Error(), "not a CloudflareTunnel") {
			t.Errorf("ValidateUpdate() error = %q, expected to contain 'not a CloudflareTunnel'", err.Error())
		}
	})

	t.Run("oldObj is not a CloudflareTunnel returns error", func(t *testing.T) {
		badObj := &wrongType{}
		_, err := validTunnel.ValidateUpdate(context.Background(), badObj, validTunnel)
		if err == nil {
			t.Errorf("ValidateUpdate() expected error when oldObj is wrong type, got nil")
		}
		if !contains(err.Error(), "not a CloudflareTunnel") {
			t.Errorf("ValidateUpdate() error = %q, expected to contain 'not a CloudflareTunnel'", err.Error())
		}
	})
}

// wrongType is a minimal runtime.Object implementation used to exercise the
// type-assertion error paths inside ValidateUpdate.
type wrongType struct {
	metav1.TypeMeta
	metav1.ObjectMeta
}

func (w *wrongType) DeepCopyObject() runtime.Object {
	return &wrongType{
		TypeMeta:   w.TypeMeta,
		ObjectMeta: *w.ObjectMeta.DeepCopy(),
	}
}
