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
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ModelCacheSpec defines the desired state of ModelCache.
type ModelCacheSpec struct {
	// Repo is the HuggingFace repository (e.g. "bartowski/Llama-3.2-1B-Instruct-GGUF")
	// +kubebuilder:validation:Required
	Repo string `json:"repo"`

	// Registry is the target OCI registry (e.g. "ghcr.io/jomcgi/models")
	// +kubebuilder:validation:Required
	Registry string `json:"registry"`

	// Revision is the HuggingFace revision (branch, tag, or commit SHA)
	// +kubebuilder:validation:Optional
	// +kubebuilder:default="main"
	Revision string `json:"revision,omitempty"`

	// File is the GGUF filename prefix selector for multi-quantization repos.
	// Required when a GGUF repo has multiple .gguf files; optional when there is exactly one.
	// Not applicable for safetensors repos.
	// +kubebuilder:validation:Optional
	File string `json:"file,omitempty"`

	// Tag overrides the OCI tag (default: derived from revision)
	// +kubebuilder:validation:Optional
	Tag string `json:"tag,omitempty"`

	// ModelDir overrides the in-image model directory path
	// +kubebuilder:validation:Optional
	ModelDir string `json:"modelDir,omitempty"`

	// TTL is the time-to-live for this cache entry (e.g. "24h", "168h")
	// +kubebuilder:validation:Optional
	TTL *metav1.Duration `json:"ttl,omitempty"`
}

// ModelCacheStatus defines the observed state of ModelCache.
type ModelCacheStatus struct {
	// Standard Kubernetes conditions
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Phase is the current state machine phase
	// +kubebuilder:validation:Enum=Pending;Resolving;Syncing;Ready;Failed
	Phase string `json:"phase,omitempty"`

	// ResolvedRef is the full OCI reference (e.g. "ghcr.io/jomcgi/models/llama-3.2:rev-abc123")
	ResolvedRef string `json:"resolvedRef,omitempty"`

	// Digest is the OCI manifest digest
	Digest string `json:"digest,omitempty"`

	// ResolvedRevision is the HuggingFace revision that was resolved
	ResolvedRevision string `json:"resolvedRevision,omitempty"`

	// Format is the detected model format (e.g. "gguf", "safetensors")
	Format string `json:"format,omitempty"`

	// FileCount is the total number of files in the model
	FileCount int `json:"fileCount,omitempty"`

	// TotalSize is the total size in bytes of all model files
	TotalSize int64 `json:"totalSize,omitempty"`

	// SyncJobName is the name of the active copy Job
	// +optional
	SyncJobName string `json:"syncJobName,omitempty"`

	// ErrorMessage contains the error that caused the Failed state
	// +optional
	ErrorMessage string `json:"errorMessage,omitempty"`

	// Permanent indicates whether the failure is non-retryable
	Permanent bool `json:"permanent,omitempty"`

	// LastState stores the state before transitioning to Failed
	// +optional
	LastState string `json:"lastState,omitempty"`

	// ObservedGeneration reflects the generation of the most recently observed spec
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// ObservedPhase stores the phase value when it was unrecognized (for Unknown state)
	// +optional
	ObservedPhase string `json:"observedPhase,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Cluster
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Repo",type=string,JSONPath=`.spec.repo`
// +kubebuilder:printcolumn:name="Format",type=string,JSONPath=`.status.format`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// ModelCache caches a HuggingFace model as an OCI artifact in a container registry.
type ModelCache struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   ModelCacheSpec   `json:"spec,omitempty"`
	Status ModelCacheStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// ModelCacheList contains a list of ModelCache.
type ModelCacheList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []ModelCache `json:"items"`
}

func init() {
	SchemeBuilder.Register(&ModelCache{}, &ModelCacheList{})
}
