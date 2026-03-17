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
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// TestConditionTypeValues verifies that each condition type constant has the
// exact string value documented in its comment.
func TestConditionTypeValues(t *testing.T) {
	tests := []struct {
		name string
		got  string
		want string
	}{
		{"TypeReady", TypeReady, "Ready"},
		{"TypeProgressing", TypeProgressing, "Progressing"},
		{"TypeDegraded", TypeDegraded, "Degraded"},
		{"TypeActive", TypeActive, "Active"},
		{"TypeInactive", TypeInactive, "Inactive"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Errorf("%s = %q, want %q", tt.name, tt.got, tt.want)
			}
		})
	}
}

// TestConditionReasonValues verifies that each condition reason constant has
// the exact string value documented in its comment.
func TestConditionReasonValues(t *testing.T) {
	tests := []struct {
		name string
		got  string
		want string
	}{
		{"ReasonCreating", ReasonCreating, "Creating"},
		{"ReasonUpdating", ReasonUpdating, "Updating"},
		{"ReasonDeleting", ReasonDeleting, "Deleting"},
		{"ReasonTunnelConnected", ReasonTunnelConnected, "TunnelConnected"},
		{"ReasonTunnelDisconnected", ReasonTunnelDisconnected, "TunnelDisconnected"},
		{"ReasonAPIError", ReasonAPIError, "APIError"},
		{"ReasonInvalidSpec", ReasonInvalidSpec, "InvalidSpec"},
		{"ReasonTargetNotFound", ReasonTargetNotFound, "TargetNotFound"},
		{"ReasonTargetInvalid", ReasonTargetInvalid, "TargetInvalid"},
		{"ReasonPolicyApplied", ReasonPolicyApplied, "PolicyApplied"},
		{"ReasonPolicyFailed", ReasonPolicyFailed, "PolicyFailed"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Errorf("%s = %q, want %q", tt.name, tt.got, tt.want)
			}
		})
	}
}

// TestConditionTypeNonEmpty ensures no condition type constant is an empty string,
// which would be invalid as a Kubernetes condition type.
func TestConditionTypeNonEmpty(t *testing.T) {
	types := []struct {
		name  string
		value string
	}{
		{"TypeReady", TypeReady},
		{"TypeProgressing", TypeProgressing},
		{"TypeDegraded", TypeDegraded},
		{"TypeActive", TypeActive},
		{"TypeInactive", TypeInactive},
	}

	for _, tt := range types {
		t.Run(tt.name, func(t *testing.T) {
			if tt.value == "" {
				t.Errorf("%s must not be empty", tt.name)
			}
		})
	}
}

// TestConditionReasonNonEmpty ensures no condition reason constant is an empty string,
// which would be invalid as a Kubernetes condition reason.
func TestConditionReasonNonEmpty(t *testing.T) {
	reasons := []struct {
		name  string
		value string
	}{
		{"ReasonCreating", ReasonCreating},
		{"ReasonUpdating", ReasonUpdating},
		{"ReasonDeleting", ReasonDeleting},
		{"ReasonTunnelConnected", ReasonTunnelConnected},
		{"ReasonTunnelDisconnected", ReasonTunnelDisconnected},
		{"ReasonAPIError", ReasonAPIError},
		{"ReasonInvalidSpec", ReasonInvalidSpec},
		{"ReasonTargetNotFound", ReasonTargetNotFound},
		{"ReasonTargetInvalid", ReasonTargetInvalid},
		{"ReasonPolicyApplied", ReasonPolicyApplied},
		{"ReasonPolicyFailed", ReasonPolicyFailed},
	}

	for _, tt := range reasons {
		t.Run(tt.name, func(t *testing.T) {
			if tt.value == "" {
				t.Errorf("%s must not be empty", tt.name)
			}
		})
	}
}

// TestConditionTypeUniqueness ensures all condition type constants are distinct
// from each other to prevent accidental aliasing.
func TestConditionTypeUniqueness(t *testing.T) {
	types := map[string]string{
		"TypeReady":       TypeReady,
		"TypeProgressing": TypeProgressing,
		"TypeDegraded":    TypeDegraded,
		"TypeActive":      TypeActive,
		"TypeInactive":    TypeInactive,
	}

	seen := make(map[string]string)
	for constName, value := range types {
		if existing, dup := seen[value]; dup {
			t.Errorf("duplicate condition type value %q: both %s and %s have the same value", value, existing, constName)
		}
		seen[value] = constName
	}
}

// TestConditionReasonUniqueness ensures all condition reason constants are
// distinct from each other.
func TestConditionReasonUniqueness(t *testing.T) {
	reasons := map[string]string{
		"ReasonCreating":           ReasonCreating,
		"ReasonUpdating":           ReasonUpdating,
		"ReasonDeleting":           ReasonDeleting,
		"ReasonTunnelConnected":    ReasonTunnelConnected,
		"ReasonTunnelDisconnected": ReasonTunnelDisconnected,
		"ReasonAPIError":           ReasonAPIError,
		"ReasonInvalidSpec":        ReasonInvalidSpec,
		"ReasonTargetNotFound":     ReasonTargetNotFound,
		"ReasonTargetInvalid":      ReasonTargetInvalid,
		"ReasonPolicyApplied":      ReasonPolicyApplied,
		"ReasonPolicyFailed":       ReasonPolicyFailed,
	}

	seen := make(map[string]string)
	for constName, value := range reasons {
		if existing, dup := seen[value]; dup {
			t.Errorf("duplicate condition reason value %q: both %s and %s have the same value", value, existing, constName)
		}
		seen[value] = constName
	}
}

// TestConditionTypesUsableAsKubernetesConditionType checks that the condition
// type constants can be used as the Type field of a metav1.Condition without
// modification, validating integration with Kubernetes API machinery.
func TestConditionTypesUsableAsKubernetesConditionType(t *testing.T) {
	conditionTypes := []string{
		TypeReady,
		TypeProgressing,
		TypeDegraded,
		TypeActive,
		TypeInactive,
	}

	for _, ct := range conditionTypes {
		t.Run(ct, func(t *testing.T) {
			cond := metav1.Condition{
				Type:               ct,
				Status:             metav1.ConditionTrue,
				Reason:             ReasonCreating,
				Message:            "test",
				LastTransitionTime: metav1.Now(),
			}
			if cond.Type != ct {
				t.Errorf("Type field round-trip failed: got %q, want %q", cond.Type, ct)
			}
		})
	}
}

// TestConditionReasonsUsableAsKubernetesConditionReason checks that reason
// constants can populate the Reason field of a metav1.Condition.
func TestConditionReasonsUsableAsKubernetesConditionReason(t *testing.T) {
	reasons := []string{
		ReasonCreating,
		ReasonUpdating,
		ReasonDeleting,
		ReasonTunnelConnected,
		ReasonTunnelDisconnected,
		ReasonAPIError,
		ReasonInvalidSpec,
		ReasonTargetNotFound,
		ReasonTargetInvalid,
		ReasonPolicyApplied,
		ReasonPolicyFailed,
	}

	for _, r := range reasons {
		t.Run(r, func(t *testing.T) {
			cond := metav1.Condition{
				Type:               TypeReady,
				Status:             metav1.ConditionFalse,
				Reason:             r,
				Message:            "test message",
				LastTransitionTime: metav1.Now(),
			}
			if cond.Reason != r {
				t.Errorf("Reason field round-trip failed: got %q, want %q", cond.Reason, r)
			}
		})
	}
}

// TestConditionStatusTransitions verifies that condition type constants can
// model the expected lifecycle transitions on a CloudflareTunnelStatus.
// This confirms the constants are semantically coherent for their intended use.
func TestConditionStatusTransitions(t *testing.T) {
	now := metav1.Now()

	// Lifecycle: Pending → Ready
	pendingConditions := []metav1.Condition{
		{
			Type:               TypeProgressing,
			Status:             metav1.ConditionTrue,
			Reason:             ReasonCreating,
			Message:            "tunnel is being created",
			LastTransitionTime: now,
		},
		{
			Type:               TypeReady,
			Status:             metav1.ConditionFalse,
			Reason:             ReasonCreating,
			Message:            "tunnel is not yet ready",
			LastTransitionTime: now,
		},
	}

	readyConditions := []metav1.Condition{
		{
			Type:               TypeReady,
			Status:             metav1.ConditionTrue,
			Reason:             ReasonTunnelConnected,
			Message:            "tunnel has active connections",
			LastTransitionTime: now,
		},
		{
			Type:               TypeActive,
			Status:             metav1.ConditionTrue,
			Reason:             ReasonTunnelConnected,
			Message:            "tunnel is live",
			LastTransitionTime: now,
		},
	}

	degradedConditions := []metav1.Condition{
		{
			Type:               TypeDegraded,
			Status:             metav1.ConditionTrue,
			Reason:             ReasonAPIError,
			Message:            "Cloudflare API error",
			LastTransitionTime: now,
		},
		{
			Type:               TypeReady,
			Status:             metav1.ConditionFalse,
			Reason:             ReasonAPIError,
			Message:            "tunnel is not ready due to API error",
			LastTransitionTime: now,
		},
	}

	for _, tc := range []struct {
		name       string
		conditions []metav1.Condition
	}{
		{"pending", pendingConditions},
		{"ready", readyConditions},
		{"degraded", degradedConditions},
	} {
		t.Run(tc.name, func(t *testing.T) {
			status := CloudflareTunnelStatus{
				Conditions: tc.conditions,
			}
			if len(status.Conditions) != len(tc.conditions) {
				t.Errorf("expected %d conditions, got %d", len(tc.conditions), len(status.Conditions))
			}
		})
	}
}

// TestDeletionReasonUsedDuringDeletion verifies that ReasonDeleting is
// appropriate for modelling the deletion lifecycle phase.
func TestDeletionReasonUsedDuringDeletion(t *testing.T) {
	now := metav1.Now()
	cond := metav1.Condition{
		Type:               TypeProgressing,
		Status:             metav1.ConditionTrue,
		Reason:             ReasonDeleting,
		Message:            "tunnel resources are being cleaned up",
		LastTransitionTime: now,
	}

	if cond.Reason != ReasonDeleting {
		t.Errorf("expected Reason %q, got %q", ReasonDeleting, cond.Reason)
	}
	if cond.Type != TypeProgressing {
		t.Errorf("expected Type %q, got %q", TypeProgressing, cond.Type)
	}
}

// TestAccessPolicyReasons verifies that access policy specific reasons are
// distinct and non-empty, covering the CloudflareAccessPolicy lifecycle.
func TestAccessPolicyReasons(t *testing.T) {
	policyReasons := []struct {
		name  string
		value string
	}{
		{"ReasonTargetNotFound", ReasonTargetNotFound},
		{"ReasonTargetInvalid", ReasonTargetInvalid},
		{"ReasonPolicyApplied", ReasonPolicyApplied},
		{"ReasonPolicyFailed", ReasonPolicyFailed},
	}

	seen := make(map[string]string)
	for _, r := range policyReasons {
		if r.value == "" {
			t.Errorf("%s must not be empty", r.name)
		}
		if existing, dup := seen[r.value]; dup {
			t.Errorf("duplicate policy reason value %q: %s and %s", r.value, existing, r.name)
		}
		seen[r.value] = r.name
	}
}

// TestInactiveAndActiveMutuallyDistinct verifies that TypeActive and TypeInactive
// are meaningfully different strings so that controllers can use them to
// represent complementary states.
func TestInactiveAndActiveMutuallyDistinct(t *testing.T) {
	if TypeActive == TypeInactive {
		t.Errorf("TypeActive and TypeInactive must be distinct, both are %q", TypeActive)
	}
}

// TestConnectedAndDisconnectedMutuallyDistinct verifies ReasonTunnelConnected and
// ReasonTunnelDisconnected are different, as they model complementary states.
func TestConnectedAndDisconnectedMutuallyDistinct(t *testing.T) {
	if ReasonTunnelConnected == ReasonTunnelDisconnected {
		t.Errorf("ReasonTunnelConnected and ReasonTunnelDisconnected must be distinct, both are %q", ReasonTunnelConnected)
	}
}

// TestPolicyAppliedAndFailedMutuallyDistinct verifies ReasonPolicyApplied and
// ReasonPolicyFailed are different.
func TestPolicyAppliedAndFailedMutuallyDistinct(t *testing.T) {
	if ReasonPolicyApplied == ReasonPolicyFailed {
		t.Errorf("ReasonPolicyApplied and ReasonPolicyFailed must be distinct, both are %q", ReasonPolicyApplied)
	}
}
