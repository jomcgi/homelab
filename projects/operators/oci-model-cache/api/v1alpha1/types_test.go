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

package v1alpha1

import (
	"bytes"
	"encoding/json"
	"reflect"
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
)

// fixedDuration is a stable duration value for use in round-trip tests.
var fixedDuration = &metav1.Duration{Duration: 24 * time.Hour}

// --- ModelCacheSpec ---

// TestModelCacheSpecJSONRoundTrip verifies ModelCacheSpec serializes and
// deserializes correctly, preserving all fields.
func TestModelCacheSpecJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name string
		spec ModelCacheSpec
	}{
		{
			name: "minimal spec (required fields only)",
			spec: ModelCacheSpec{
				Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
				Registry: "ghcr.io/jomcgi/models",
			},
		},
		{
			name: "spec with all optional fields",
			spec: ModelCacheSpec{
				Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
				Registry: "ghcr.io/jomcgi/models",
				Revision: "main",
				File:     "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
				Tag:      "v1.0.0",
				ModelDir: "/models/llama",
				TTL:      fixedDuration,
			},
		},
		{
			name: "spec with revision only",
			spec: ModelCacheSpec{
				Repo:     "meta-llama/Llama-2-7b-hf",
				Registry: "registry.example.com/models",
				Revision: "abc123def456",
			},
		},
		{
			name: "spec with TTL nil",
			spec: ModelCacheSpec{
				Repo:     "Qwen/Qwen2.5-0.5B",
				Registry: "ghcr.io/jomcgi/models",
				TTL:      nil,
			},
		},
		{
			name: "spec with TTL 168h (weekly)",
			spec: ModelCacheSpec{
				Repo:     "mistralai/Mistral-7B-v0.1",
				Registry: "ghcr.io/jomcgi/models",
				TTL:      &metav1.Duration{Duration: 168 * time.Hour},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.spec)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got ModelCacheSpec
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if !reflect.DeepEqual(tt.spec, got) {
				t.Errorf("round-trip mismatch: want %+v, got %+v", tt.spec, got)
			}
		})
	}
}

// TestModelCacheSpecJSONFieldNames verifies that ModelCacheSpec uses the
// expected JSON field names (camelCase) and omitempty works correctly.
func TestModelCacheSpecJSONFieldNames(t *testing.T) {
	spec := ModelCacheSpec{
		Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
		Registry: "ghcr.io/jomcgi/models",
		Revision: "main",
		File:     "model.gguf",
		Tag:      "latest",
		ModelDir: "/models",
		TTL:      fixedDuration,
	}

	data, err := json.Marshal(spec)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	expectedKeys := []string{"repo", "registry", "revision", "file", "tag", "modelDir", "ttl"}
	for _, key := range expectedKeys {
		if _, ok := raw[key]; !ok {
			t.Errorf("expected JSON key %q to be present", key)
		}
	}
}

// TestModelCacheSpecOmitemptyFields verifies optional fields are omitted
// when empty (omitempty), and required fields are always present.
func TestModelCacheSpecOmitemptyFields(t *testing.T) {
	// Only required fields set
	spec := ModelCacheSpec{
		Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
		Registry: "ghcr.io/jomcgi/models",
	}

	data, err := json.Marshal(spec)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	// Required fields must always be present
	for _, key := range []string{"repo", "registry"} {
		if _, ok := raw[key]; !ok {
			t.Errorf("required field %q should always be present", key)
		}
	}

	// Optional fields must be omitted when empty/nil
	for _, key := range []string{"revision", "file", "tag", "modelDir", "ttl"} {
		if _, ok := raw[key]; ok {
			t.Errorf("optional field %q should be omitted when empty (omitempty)", key)
		}
	}
}

// --- ModelCacheStatus ---

// TestModelCacheStatusJSONRoundTrip verifies ModelCacheStatus serializes and
// deserializes correctly with all field combinations.
func TestModelCacheStatusJSONRoundTrip(t *testing.T) {
	fixedTime := metav1.NewTime(time.Date(2025, 1, 15, 10, 30, 0, 0, time.UTC))

	tests := []struct {
		name   string
		status ModelCacheStatus
	}{
		{
			name:   "empty status",
			status: ModelCacheStatus{},
		},
		{
			name: "ready status with all fields",
			status: ModelCacheStatus{
				Phase:              "Ready",
				ResolvedRef:        "ghcr.io/jomcgi/models/llama-3.2:rev-abc123",
				Digest:             "sha256:abc123",
				ResolvedRevision:   "abc123def456",
				Format:             "gguf",
				FileCount:          1,
				TotalSize:          4294967296,
				ObservedGeneration: 3,
			},
		},
		{
			name: "failed status with error",
			status: ModelCacheStatus{
				Phase:        "Failed",
				ErrorMessage: "failed to pull model: connection refused",
				Permanent:    true,
				LastState:    "Syncing",
			},
		},
		{
			name: "syncing status with job name",
			status: ModelCacheStatus{
				Phase:       "Syncing",
				SyncJobName: "modelcache-llama-sync-12345",
			},
		},
		{
			name: "status with conditions",
			status: ModelCacheStatus{
				Phase: "Ready",
				Conditions: []metav1.Condition{
					{
						Type:               "Ready",
						Status:             metav1.ConditionTrue,
						ObservedGeneration: 1,
						LastTransitionTime: fixedTime,
						Reason:             "Synced",
						Message:            "Model is ready",
					},
				},
			},
		},
		{
			name: "resolving status with observed phase",
			status: ModelCacheStatus{
				Phase:         "Unknown",
				ObservedPhase: "CustomPhase",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.status)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got ModelCacheStatus
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			// Compare via JSON bytes to avoid metav1.Time timezone pointer
			// differences that cause reflect.DeepEqual to fail even when the
			// time values are identical (same instant, different *Location ptr).
			gotData, err := json.Marshal(got)
			if err != nil {
				t.Fatalf("re-Marshal() error = %v", err)
			}
			if !bytes.Equal(data, gotData) {
				t.Errorf("round-trip mismatch: want %s, got %s", data, gotData)
			}
		})
	}
}

// TestModelCacheStatusJSONFieldNames verifies ModelCacheStatus uses the
// expected JSON field names (camelCase).
func TestModelCacheStatusJSONFieldNames(t *testing.T) {
	status := ModelCacheStatus{
		Phase:              "Ready",
		ResolvedRef:        "ghcr.io/jomcgi/models/llama:rev-abc",
		Digest:             "sha256:abc",
		ResolvedRevision:   "abc123",
		Format:             "gguf",
		FileCount:          2,
		TotalSize:          1024,
		SyncJobName:        "sync-job-1",
		ErrorMessage:       "some error",
		Permanent:          true,
		LastState:          "Syncing",
		ObservedGeneration: 5,
		ObservedPhase:      "CustomPhase",
	}

	data, err := json.Marshal(status)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	expectedKeys := []string{
		"phase", "resolvedRef", "digest", "resolvedRevision", "format",
		"fileCount", "totalSize", "syncJobName", "errorMessage", "permanent",
		"lastState", "observedGeneration", "observedPhase",
	}
	for _, key := range expectedKeys {
		if _, ok := raw[key]; !ok {
			t.Errorf("expected JSON key %q to be present", key)
		}
	}
}

// TestModelCacheStatusOmitemptyFields verifies that optional status fields
// are omitted when empty.
func TestModelCacheStatusOmitemptyFields(t *testing.T) {
	// Empty status should produce minimal JSON
	status := ModelCacheStatus{}

	data, err := json.Marshal(status)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	// All fields are omitempty, so an empty status should produce {}
	if len(raw) != 0 {
		t.Errorf("empty status should produce empty JSON object {}, got keys: %v", raw)
	}
}

// TestModelCacheStatusPhaseValues verifies the known phase values are valid
// strings that match the kubebuilder enum.
func TestModelCacheStatusPhaseValues(t *testing.T) {
	knownPhases := []string{"Pending", "Resolving", "Syncing", "Ready", "Failed"}

	for _, phase := range knownPhases {
		t.Run(phase, func(t *testing.T) {
			status := ModelCacheStatus{Phase: phase}
			data, err := json.Marshal(status)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got ModelCacheStatus
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			if got.Phase != phase {
				t.Errorf("phase round-trip: want %q, got %q", phase, got.Phase)
			}
		})
	}
}

// --- ModelCache ---

// TestModelCacheJSONRoundTrip verifies the full ModelCache resource serializes
// and deserializes correctly, including TypeMeta and ObjectMeta.
func TestModelCacheJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name  string
		cache ModelCache
	}{
		{
			name:  "empty resource",
			cache: ModelCache{},
		},
		{
			name: "minimal resource",
			cache: ModelCache{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
					Kind:       "ModelCache",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name: "llama-3-2-1b",
				},
				Spec: ModelCacheSpec{
					Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
					Registry: "ghcr.io/jomcgi/models",
				},
			},
		},
		{
			name: "full resource with status",
			cache: ModelCache{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
					Kind:       "ModelCache",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name:       "llama-3-2-1b",
					Generation: 2,
				},
				Spec: ModelCacheSpec{
					Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
					Registry: "ghcr.io/jomcgi/models",
					Revision: "main",
					File:     "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
					TTL:      &metav1.Duration{Duration: 24 * time.Hour},
				},
				Status: ModelCacheStatus{
					Phase:              "Ready",
					ResolvedRef:        "ghcr.io/jomcgi/models/llama-3.2:rev-abc123",
					Digest:             "sha256:abc123",
					Format:             "gguf",
					FileCount:          1,
					TotalSize:          2147483648,
					ObservedGeneration: 2,
				},
			},
		},
		{
			name: "cluster-scoped resource (no namespace)",
			cache: ModelCache{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
					Kind:       "ModelCache",
				},
				ObjectMeta: metav1.ObjectMeta{
					Name: "qwen-0-5b",
					Labels: map[string]string{
						"app.kubernetes.io/managed-by": "oci-model-cache-operator",
					},
				},
				Spec: ModelCacheSpec{
					Repo:     "Qwen/Qwen2.5-0.5B",
					Registry: "ghcr.io/jomcgi/models",
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.cache)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got ModelCache
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			// Compare via JSON bytes to avoid metav1.Time timezone pointer
			// differences in ObjectMeta timestamps after round-trip.
			gotData, err := json.Marshal(got)
			if err != nil {
				t.Fatalf("re-Marshal() error = %v", err)
			}
			if !bytes.Equal(data, gotData) {
				t.Errorf("round-trip mismatch: want %s, got %s", data, gotData)
			}
		})
	}
}

// TestModelCacheJSONTopLevelFieldNames verifies the top-level JSON field names
// of a ModelCache resource match the Kubernetes convention.
func TestModelCacheJSONTopLevelFieldNames(t *testing.T) {
	cache := ModelCache{
		TypeMeta: metav1.TypeMeta{
			APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
			Kind:       "ModelCache",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name: "test-model",
		},
		Spec: ModelCacheSpec{
			Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
			Registry: "ghcr.io/jomcgi/models",
		},
		Status: ModelCacheStatus{
			Phase: "Ready",
		},
	}

	data, err := json.Marshal(cache)
	if err != nil {
		t.Fatalf("Marshal() error = %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map error = %v", err)
	}

	for _, key := range []string{"apiVersion", "kind", "metadata", "spec", "status"} {
		if _, ok := raw[key]; !ok {
			t.Errorf("expected top-level JSON key %q to be present", key)
		}
	}
}

// --- ModelCacheList ---

// TestModelCacheListJSONRoundTrip verifies ModelCacheList serializes and
// deserializes correctly, including empty and populated item lists.
func TestModelCacheListJSONRoundTrip(t *testing.T) {
	tests := []struct {
		name string
		list ModelCacheList
	}{
		{
			name: "empty list",
			list: ModelCacheList{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
					Kind:       "ModelCacheList",
				},
				Items: []ModelCache{},
			},
		},
		{
			name: "list with one item",
			list: ModelCacheList{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
					Kind:       "ModelCacheList",
				},
				Items: []ModelCache{
					{
						ObjectMeta: metav1.ObjectMeta{Name: "llama-3-2-1b"},
						Spec: ModelCacheSpec{
							Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
							Registry: "ghcr.io/jomcgi/models",
						},
					},
				},
			},
		},
		{
			name: "list with multiple items",
			list: ModelCacheList{
				TypeMeta: metav1.TypeMeta{
					APIVersion: "oci-model-cache.jomcgi.dev/v1alpha1",
					Kind:       "ModelCacheList",
				},
				Items: []ModelCache{
					{
						ObjectMeta: metav1.ObjectMeta{Name: "llama-3-2-1b"},
						Spec: ModelCacheSpec{
							Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
							Registry: "ghcr.io/jomcgi/models",
						},
					},
					{
						ObjectMeta: metav1.ObjectMeta{Name: "qwen-0-5b"},
						Spec: ModelCacheSpec{
							Repo:     "Qwen/Qwen2.5-0.5B",
							Registry: "ghcr.io/jomcgi/models",
						},
						Status: ModelCacheStatus{Phase: "Ready"},
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := json.Marshal(tt.list)
			if err != nil {
				t.Fatalf("Marshal() error = %v", err)
			}
			var got ModelCacheList
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatalf("Unmarshal() error = %v", err)
			}
			// Compare via JSON bytes to avoid metav1.Time timezone pointer
			// differences after round-trip.
			gotData, err := json.Marshal(got)
			if err != nil {
				t.Fatalf("re-Marshal() error = %v", err)
			}
			if !bytes.Equal(data, gotData) {
				t.Errorf("round-trip mismatch: want %s, got %s", data, gotData)
			}
		})
	}
}

// --- DeepCopy ---

// TestModelCacheDeepCopyNilReceiver verifies that DeepCopy on a nil
// *ModelCache returns nil without panicking.
func TestModelCacheDeepCopyNilReceiver(t *testing.T) {
	var mc *ModelCache
	if got := mc.DeepCopy(); got != nil {
		t.Errorf("DeepCopy() on nil receiver: want nil, got %+v", got)
	}
}

// TestModelCacheListDeepCopyNilReceiver verifies that DeepCopy on a nil
// *ModelCacheList returns nil without panicking.
func TestModelCacheListDeepCopyNilReceiver(t *testing.T) {
	var mcl *ModelCacheList
	if got := mcl.DeepCopy(); got != nil {
		t.Errorf("DeepCopy() on nil receiver: want nil, got %+v", got)
	}
}

// TestModelCacheSpecDeepCopyNilReceiver verifies that DeepCopy on a nil
// *ModelCacheSpec returns nil without panicking.
func TestModelCacheSpecDeepCopyNilReceiver(t *testing.T) {
	var mcs *ModelCacheSpec
	if got := mcs.DeepCopy(); got != nil {
		t.Errorf("DeepCopy() on nil receiver: want nil, got %+v", got)
	}
}

// TestModelCacheStatusDeepCopyNilReceiver verifies that DeepCopy on a nil
// *ModelCacheStatus returns nil without panicking.
func TestModelCacheStatusDeepCopyNilReceiver(t *testing.T) {
	var mcs *ModelCacheStatus
	if got := mcs.DeepCopy(); got != nil {
		t.Errorf("DeepCopy() on nil receiver: want nil, got %+v", got)
	}
}

// TestModelCacheDeepCopyMutationIsolation verifies that mutating a deep-copied
// ModelCache does not affect the original.
func TestModelCacheDeepCopyMutationIsolation(t *testing.T) {
	original := &ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name: "llama-3-2-1b",
			Labels: map[string]string{
				"env": "production",
			},
		},
		Spec: ModelCacheSpec{
			Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
			Registry: "ghcr.io/jomcgi/models",
			TTL:      &metav1.Duration{Duration: 24 * time.Hour},
		},
		Status: ModelCacheStatus{
			Phase: "Ready",
			Conditions: []metav1.Condition{
				{
					Type:   "Ready",
					Status: metav1.ConditionTrue,
				},
			},
		},
	}

	copy := original.DeepCopy()

	// Mutate the copy
	copy.Name = "mutated-name"
	copy.Labels["env"] = "staging"
	copy.Spec.Repo = "mutated/repo"
	copy.Spec.TTL.Duration = 48 * time.Hour
	copy.Status.Phase = "Failed"
	copy.Status.Conditions[0].Status = metav1.ConditionFalse

	// Verify original is unaffected
	if original.Name != "llama-3-2-1b" {
		t.Errorf("original Name mutated: want %q, got %q", "llama-3-2-1b", original.Name)
	}
	if original.Labels["env"] != "production" {
		t.Errorf("original Labels mutated: want %q, got %q", "production", original.Labels["env"])
	}
	if original.Spec.Repo != "bartowski/Llama-3.2-1B-Instruct-GGUF" {
		t.Errorf("original Spec.Repo mutated: want %q, got %q", "bartowski/Llama-3.2-1B-Instruct-GGUF", original.Spec.Repo)
	}
	if original.Spec.TTL.Duration != 24*time.Hour {
		t.Errorf("original Spec.TTL mutated: want 24h, got %v", original.Spec.TTL.Duration)
	}
	if original.Status.Phase != "Ready" {
		t.Errorf("original Status.Phase mutated: want %q, got %q", "Ready", original.Status.Phase)
	}
	if original.Status.Conditions[0].Status != metav1.ConditionTrue {
		t.Errorf("original Status.Conditions mutated: want %q, got %q", metav1.ConditionTrue, original.Status.Conditions[0].Status)
	}
}

// TestModelCacheListDeepCopyMutationIsolation verifies that mutating a
// deep-copied ModelCacheList does not affect the original.
func TestModelCacheListDeepCopyMutationIsolation(t *testing.T) {
	original := &ModelCacheList{
		Items: []ModelCache{
			{
				ObjectMeta: metav1.ObjectMeta{Name: "item-0"},
				Spec: ModelCacheSpec{
					Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
					Registry: "ghcr.io/jomcgi/models",
				},
			},
		},
	}

	copy := original.DeepCopy()

	// Mutate the copy's items
	copy.Items[0].Name = "mutated"
	copy.Items[0].Spec.Repo = "mutated/repo"

	if original.Items[0].Name != "item-0" {
		t.Errorf("original Items[0].Name mutated: want %q, got %q", "item-0", original.Items[0].Name)
	}
	if original.Items[0].Spec.Repo != "bartowski/Llama-3.2-1B-Instruct-GGUF" {
		t.Errorf("original Items[0].Spec.Repo mutated: want %q, got %q",
			"bartowski/Llama-3.2-1B-Instruct-GGUF", original.Items[0].Spec.Repo)
	}
}

// --- Scheme registration ---

// TestSchemeRegistration verifies that ModelCache and ModelCacheList are
// registered in the scheme via AddToScheme.
func TestSchemeRegistration(t *testing.T) {
	scheme := runtime.NewScheme()
	if err := AddToScheme(scheme); err != nil {
		t.Fatalf("AddToScheme() error = %v", err)
	}

	// Verify ModelCache is registered
	gvk, _, err := scheme.ObjectKinds(&ModelCache{})
	if err != nil {
		t.Fatalf("scheme.ObjectKinds(ModelCache) error = %v", err)
	}
	if len(gvk) == 0 {
		t.Fatal("expected ModelCache to be registered, got no GVKs")
	}
	if gvk[0].Group != "oci-model-cache.jomcgi.dev" {
		t.Errorf("ModelCache Group: want %q, got %q", "oci-model-cache.jomcgi.dev", gvk[0].Group)
	}
	if gvk[0].Version != "v1alpha1" {
		t.Errorf("ModelCache Version: want %q, got %q", "v1alpha1", gvk[0].Version)
	}
	if gvk[0].Kind != "ModelCache" {
		t.Errorf("ModelCache Kind: want %q, got %q", "ModelCache", gvk[0].Kind)
	}

	// Verify ModelCacheList is registered
	listGVK, _, err := scheme.ObjectKinds(&ModelCacheList{})
	if err != nil {
		t.Fatalf("scheme.ObjectKinds(ModelCacheList) error = %v", err)
	}
	if len(listGVK) == 0 {
		t.Fatal("expected ModelCacheList to be registered, got no GVKs")
	}
	if listGVK[0].Kind != "ModelCacheList" {
		t.Errorf("ModelCacheList Kind: want %q, got %q", "ModelCacheList", listGVK[0].Kind)
	}
}
