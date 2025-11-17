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
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"
)

// Gateway API Policy Attachment condition types (GEP-713)
const (
	// TypeAccepted indicates whether the policy has been accepted and attached to the target.
	TypeAccepted = "Accepted"

	// TypeResolvedRefs indicates whether all references (targetRef, etc.) have been resolved.
	TypeResolvedRefs = "ResolvedRefs"

	// TypeProgrammed indicates whether the policy has been programmed into Cloudflare.
	TypeProgrammed = "Programmed"
)

// Condition reasons for CloudflareAccessPolicy
const (
	// ReasonAccepted indicates the policy was accepted.
	ReasonAccepted = "Accepted"

	// ReasonInvalid indicates the policy spec is invalid.
	ReasonInvalid = "Invalid"

	// ReasonRefNotPermitted indicates a reference is not permitted.
	ReasonRefNotPermitted = "RefNotPermitted"

	// ReasonProgrammed indicates the policy is programmed in Cloudflare.
	ReasonProgrammed = "Programmed"

	// ReasonCloudflareError indicates a Cloudflare API error occurred.
	ReasonCloudflareError = "CloudflareError"
)

// Note: ReasonTargetNotFound is defined in conditions.go

// PolicyTargetReference identifies an API object to apply policy to.
// Compatible with Gateway API Policy Attachment (GEP-713).
type PolicyTargetReference struct {
	// Group is the group of the target resource.
	// +kubebuilder:default=gateway.networking.k8s.io
	Group string `json:"group"`

	// Kind is the kind of the target resource.
	// Supported values: HTTPRoute, Gateway
	// +kubebuilder:validation:Enum=HTTPRoute;Gateway
	Kind string `json:"kind"`

	// Name is the name of the target resource.
	// +kubebuilder:validation:MinLength=1
	// +kubebuilder:validation:MaxLength=253
	Name string `json:"name"`

	// Namespace is the namespace of the target resource.
	// When unspecified, the local namespace is inferred.
	// +optional
	Namespace *gatewayv1.Namespace `json:"namespace,omitempty"`
}

// AccessPolicyRule defines a rule for an access policy.
type AccessPolicyRule struct {
	// Name is the rule name for identification.
	// +optional
	Name string `json:"name,omitempty"`

	// EmailsEndingIn matches emails ending with specified domains.
	// Example: ["@company.com", "@contractor.com"]
	// +optional
	EmailsEndingIn []string `json:"emailsEndingIn,omitempty"`

	// Emails matches specific email addresses.
	// Example: ["user@example.com"]
	// +optional
	Emails []string `json:"emails,omitempty"`

	// EmailDomains matches users from specific email domains.
	// Example: ["example.com"]
	// +optional
	EmailDomains []string `json:"emailDomains,omitempty"`

	// IPRanges matches requests from specific IP ranges (CIDR notation).
	// Example: ["192.168.1.0/24", "10.0.0.1/32"]
	// +optional
	IPRanges []string `json:"ipRanges,omitempty"`

	// Everyone matches all users (use with caution).
	// +optional
	Everyone bool `json:"everyone,omitempty"`

	// GitHubUsers matches specific GitHub usernames.
	// Requires GitHub OAuth integration.
	// +optional
	GitHubUsers []string `json:"githubUsers,omitempty"`

	// GitHubOrganizations matches users from specific GitHub organizations.
	// Requires GitHub OAuth integration.
	// +optional
	GitHubOrganizations []string `json:"githubOrganizations,omitempty"`

	// Countries matches requests from specific countries (ISO 3166-1 alpha-2).
	// Example: ["US", "GB", "CA"]
	// +optional
	Countries []string `json:"countries,omitempty"`
}

// AccessPolicy defines an access policy with decision and rules.
type AccessPolicy struct {
	// Name is the policy name for identification.
	// +optional
	Name string `json:"name,omitempty"`

	// Decision specifies the policy decision.
	// +kubebuilder:validation:Enum=allow;deny;non_identity;bypass
	// +kubebuilder:default=allow
	Decision string `json:"decision"`

	// Rules specify the conditions for this policy.
	// At least one rule must be specified.
	// +kubebuilder:validation:MinItems=1
	Rules []AccessPolicyRule `json:"rules"`

	// ExternalPolicyID references an existing Cloudflare policy by ID.
	// When set, this policy is not created but linked from Cloudflare.
	// Mutually exclusive with Decision and Rules.
	// +optional
	ExternalPolicyID string `json:"externalPolicyID,omitempty"`
}

// CORSHeaders defines CORS configuration for the access application.
type CORSHeaders struct {
	// AllowAllOrigins allows all origins.
	// +optional
	AllowAllOrigins bool `json:"allowAllOrigins,omitempty"`

	// AllowedOrigins specifies allowed origins.
	// Example: ["https://example.com", "https://app.example.com"]
	// +optional
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`

	// AllowedMethods specifies allowed HTTP methods.
	// Example: ["GET", "POST", "PUT", "DELETE"]
	// +optional
	AllowedMethods []string `json:"allowedMethods,omitempty"`

	// AllowedHeaders specifies allowed HTTP headers.
	// Example: ["Content-Type", "Authorization"]
	// +optional
	AllowedHeaders []string `json:"allowedHeaders,omitempty"`

	// AllowCredentials allows credentials in requests.
	// +optional
	AllowCredentials bool `json:"allowCredentials,omitempty"`

	// MaxAge specifies the max age for preflight cache (seconds).
	// +optional
	MaxAge *int `json:"maxAge,omitempty"`
}

// ApplicationConfig defines the access application configuration.
type ApplicationConfig struct {
	// Name is the application name displayed in Cloudflare Access.
	// Defaults to the target HTTPRoute hostname if not specified.
	// +optional
	Name string `json:"name,omitempty"`

	// Domain is the application domain.
	// Automatically inferred from HTTPRoute hostname if not specified.
	// +optional
	Domain string `json:"domain,omitempty"`

	// Type specifies the application type.
	// +kubebuilder:validation:Enum=self_hosted;saas;ssh;vnc;app_launcher;warp;biso;bookmark
	// +kubebuilder:default=self_hosted
	Type string `json:"type,omitempty"`

	// SessionDuration specifies how long a session lasts.
	// Examples: "24h", "1h30m", "30m"
	// +kubebuilder:default="24h"
	SessionDuration string `json:"sessionDuration,omitempty"`

	// CORSHeaders specifies CORS configuration.
	// +optional
	CORSHeaders *CORSHeaders `json:"corsHeaders,omitempty"`

	// AutoRedirectToIdentity enables automatic redirect to identity provider.
	// +optional
	AutoRedirectToIdentity bool `json:"autoRedirectToIdentity,omitempty"`

	// EnableBindingCookie enables binding cookie for additional security.
	// +optional
	EnableBindingCookie bool `json:"enableBindingCookie,omitempty"`

	// CustomDenyMessage is shown to users who are denied access.
	// +optional
	CustomDenyMessage string `json:"customDenyMessage,omitempty"`

	// CustomDenyURL redirects denied users to a custom URL.
	// +optional
	CustomDenyURL string `json:"customDenyURL,omitempty"`
}

// CloudflareAccessPolicySpec defines the desired state of CloudflareAccessPolicy.
// Implements Gateway API Policy Attachment pattern (GEP-713).
type CloudflareAccessPolicySpec struct {
	// TargetRef identifies the Gateway API resource to apply policy to.
	// Supports HTTPRoute and Gateway resources.
	// +kubebuilder:validation:Required
	TargetRef PolicyTargetReference `json:"targetRef"`

	// Application specifies the access application configuration.
	// +optional
	Application ApplicationConfig `json:"application,omitempty"`

	// Policies specify the access policies to apply.
	// At least one policy must be specified.
	// +kubebuilder:validation:MinItems=1
	Policies []AccessPolicy `json:"policies"`
}

// CloudflareAccessPolicyStatus defines the observed state of CloudflareAccessPolicy.
type CloudflareAccessPolicyStatus struct {
	// Conditions describe the current state of the access policy.
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// ApplicationID is the Cloudflare Access application ID.
	// +optional
	ApplicationID string `json:"applicationId,omitempty"`

	// PolicyIDs are the Cloudflare policy IDs associated with this resource.
	// +optional
	PolicyIDs []string `json:"policyIds,omitempty"`

	// TargetDomain is the domain this policy applies to (resolved from target).
	// +optional
	TargetDomain string `json:"targetDomain,omitempty"`

	// ObservedGeneration reflects the generation of the most recently observed spec.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:categories=gateway-api
// +kubebuilder:printcolumn:name="Target Kind",type=string,JSONPath=`.spec.targetRef.kind`
// +kubebuilder:printcolumn:name="Target Name",type=string,JSONPath=`.spec.targetRef.name`
// +kubebuilder:printcolumn:name="Domain",type=string,JSONPath=`.status.targetDomain`
// +kubebuilder:printcolumn:name="Ready",type=string,JSONPath=`.status.conditions[?(@.type=="Ready")].status`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// CloudflareAccessPolicy is the Schema for the cloudflareaccesspolicies API.
// This CRD implements Gateway API Policy Attachment (GEP-713) to attach
// Cloudflare Zero Trust access policies to HTTPRoute or Gateway resources.
type CloudflareAccessPolicy struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   CloudflareAccessPolicySpec   `json:"spec,omitempty"`
	Status CloudflareAccessPolicyStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// CloudflareAccessPolicyList contains a list of CloudflareAccessPolicy.
type CloudflareAccessPolicyList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []CloudflareAccessPolicy `json:"items"`
}

func init() {
	SchemeBuilder.Register(&CloudflareAccessPolicy{}, &CloudflareAccessPolicyList{})
}
