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
	corev1 "k8s.io/api/core/v1"
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

// DaemonConfig defines configuration for the cloudflared daemon
type DaemonConfig struct {
	// Enabled controls whether the operator should deploy cloudflared daemon
	// +kubebuilder:default=true
	Enabled bool `json:"enabled,omitempty"`

	// Image specifies the cloudflared container image
	// +kubebuilder:default="cloudflare/cloudflared:latest"
	Image string `json:"image,omitempty"`

	// Replicas specifies the number of daemon replicas
	// +kubebuilder:default=2
	// +kubebuilder:validation:Minimum=1
	Replicas *int32 `json:"replicas,omitempty"`

	// Resources specifies the resource requirements for the daemon
	Resources corev1.ResourceRequirements `json:"resources,omitempty"`

	// NodeSelector specifies node selection constraints
	NodeSelector map[string]string `json:"nodeSelector,omitempty"`

	// Tolerations specifies the tolerations for the daemon pods
	Tolerations []corev1.Toleration `json:"tolerations,omitempty"`

	// Affinity specifies the affinity rules for the daemon pods
	Affinity *corev1.Affinity `json:"affinity,omitempty"`

	// SecretRef specifies the secret containing tunnel credentials
	// If not provided, the operator will create and manage the secret
	SecretRef *SecretReference `json:"secretRef,omitempty"`

	// ServiceAccount specifies the service account to use for the daemon
	ServiceAccount string `json:"serviceAccount,omitempty"`

	// Annotations specifies additional annotations for daemon pods
	Annotations map[string]string `json:"annotations,omitempty"`

	// Labels specifies additional labels for daemon pods
	Labels map[string]string `json:"labels,omitempty"`
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

	// Daemon specifies the cloudflared daemon configuration
	// +kubebuilder:validation:Optional
	Daemon *DaemonConfig `json:"daemon,omitempty"`
}

// CloudflareTunnelStatus defines the observed state of CloudflareTunnel.
type CloudflareTunnelStatus struct {
	// Standard Kubernetes conditions
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// TunnelID is the Cloudflare tunnel ID
	TunnelID string `json:"tunnelId,omitempty"`

	// Active indicates if the tunnel has active connections
	Active bool `json:"active"`

	// Ready indicates if the tunnel is ready for use
	Ready bool `json:"ready"`

	// ObservedGeneration reflects the generation of the most recently observed spec
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// TunnelSecret is the name of the secret containing tunnel credentials
	TunnelSecret string `json:"tunnelSecret,omitempty"`

	// DaemonStatus provides information about the daemon deployment
	DaemonStatus *DaemonStatus `json:"daemonStatus,omitempty"`
}

// DaemonStatus provides status information about the cloudflared daemon
type DaemonStatus struct {
	// Enabled indicates if daemon management is enabled
	Enabled bool `json:"enabled"`

	// Replicas indicates the number of daemon replicas
	Replicas int32 `json:"replicas"`

	// ReadyReplicas indicates the number of ready daemon replicas
	ReadyReplicas int32 `json:"readyReplicas"`

	// DeploymentName is the name of the daemon deployment
	DeploymentName string `json:"deploymentName,omitempty"`

	// SecretName is the name of the tunnel secret
	SecretName string `json:"secretName,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status

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
