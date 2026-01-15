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
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// EDIT THIS FILE!  THIS IS SCAFFOLDING FOR YOU TO OWN!
// NOTE: json tags are required.  Any new fields you add must have json tags for the fields to be serialized.

// TunnelIngress defines ingress rules for the tunnel
type TunnelIngress struct {
	// Hostname specifies the hostname to route traffic from
	Hostname string `json:"hostname,omitempty"`
	// Service specifies the target service URL
	Service string `json:"service"`
}

// SecretReference defines a reference to a Kubernetes secret
type SecretReference struct {
	// Name is the name of the secret
	Name string `json:"name"`
	// Key is the key within the secret
	// +kubebuilder:default="tunnel-secret"
	Key string `json:"key,omitempty"`
}

// CloudflareTunnelSpec defines the desired state of CloudflareTunnel.
type CloudflareTunnelSpec struct {
	// Name specifies the tunnel name in Cloudflare
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// AccountID specifies the Cloudflare account ID
	// +kubebuilder:validation:Required
	AccountID string `json:"accountId"`

	// ConfigSource specifies the configuration source
	// +kubebuilder:validation:Optional
	// +kubebuilder:default="cloudflare"
	ConfigSource string `json:"configSource,omitempty"`

	// Ingress specifies the ingress rules for the tunnel
	// +kubebuilder:validation:Optional
	Ingress []TunnelIngress `json:"ingress,omitempty"`
}

// CloudflareTunnelStatus defines the observed state of CloudflareTunnel.
type CloudflareTunnelStatus struct {
	// Standard Kubernetes conditions
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Phase is the current state machine phase
	// +kubebuilder:validation:Enum=Pending;CreatingTunnel;CreatingSecret;ConfiguringIngress;Ready;Failed;DeletingTunnel;Deleted;Unknown
	Phase string `json:"phase,omitempty"`

	// TunnelID is the Cloudflare tunnel ID
	TunnelID string `json:"tunnelId,omitempty"`

	// SecretName is the name of the Secret containing the tunnel credentials
	// +optional
	SecretName string `json:"secretName,omitempty"`

	// Active indicates if the tunnel has active connections
	Active bool `json:"active"`

	// Ready indicates if the tunnel is ready for use
	Ready bool `json:"ready"`

	// ObservedGeneration reflects the generation of the most recently observed spec
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// LastState stores the state before transitioning to Failed
	// +optional
	LastState string `json:"lastState,omitempty"`

	// ErrorMessage contains the error that caused the Failed state
	// +optional
	ErrorMessage string `json:"errorMessage,omitempty"`

	// RetryCount tracks retry attempts from Failed state
	// +optional
	RetryCount int `json:"retryCount,omitempty"`

	// ObservedPhase stores the phase value when it was unrecognized (for Unknown state)
	// +optional
	ObservedPhase string `json:"observedPhase,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="TunnelID",type=string,JSONPath=`.status.tunnelId`
// +kubebuilder:printcolumn:name="Active",type=boolean,JSONPath=`.status.active`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// CloudflareTunnel is the Schema for the cloudflaretunnels API.
type CloudflareTunnel struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   CloudflareTunnelSpec   `json:"spec,omitempty"`
	Status CloudflareTunnelStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// CloudflareTunnelList contains a list of CloudflareTunnel.
type CloudflareTunnelList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []CloudflareTunnel `json:"items"`
}

func init() {
	SchemeBuilder.Register(&CloudflareTunnel{}, &CloudflareTunnelList{})
}
