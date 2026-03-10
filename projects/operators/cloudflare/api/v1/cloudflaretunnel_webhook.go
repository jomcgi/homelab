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
	"fmt"
	"regexp"
	"strings"

	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/validation/field"
	ctrl "sigs.k8s.io/controller-runtime"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"
)

// log is for logging in this package.
var cloudflaretunnellog = logf.Log.WithName("cloudflaretunnel-resource")

// SetupWebhookWithManager sets up the webhook with the Manager
func (r *CloudflareTunnel) SetupWebhookWithManager(mgr ctrl.Manager) error {
	return ctrl.NewWebhookManagedBy(mgr).
		For(r).
		Complete()
}

// +kubebuilder:webhook:path=/validate-tunnels-cloudflare-io-v1-cloudflaretunnel,mutating=false,failurePolicy=fail,sideEffects=None,groups=tunnels.cloudflare.io,resources=cloudflaretunnels,verbs=create;update,versions=v1,name=vcloudflaretunnel.kb.io,admissionReviewVersions=v1

var _ admission.CustomValidator = &CloudflareTunnel{}

// ValidateCreate implements admission.CustomValidator so a webhook will be registered for the type
func (r *CloudflareTunnel) ValidateCreate(ctx context.Context, obj runtime.Object) (admission.Warnings, error) {
	cloudflaretunnellog.Info("validate create", "name", r.Name)

	var allErrs field.ErrorList

	// Validate AccountID is required
	if r.Spec.AccountID == "" {
		allErrs = append(allErrs, field.Required(
			field.NewPath("spec", "accountID"),
			"accountID is required",
		))
	}

	// Validate ingress rules if present
	if err := r.validateIngressRules(); err != nil {
		allErrs = append(allErrs, err...)
	}

	if len(allErrs) == 0 {
		return nil, nil
	}

	return nil, fmt.Errorf("validation failed: %v", allErrs.ToAggregate())
}

// ValidateUpdate implements admission.CustomValidator so a webhook will be registered for the type
func (r *CloudflareTunnel) ValidateUpdate(ctx context.Context, oldObj, newObj runtime.Object) (admission.Warnings, error) {
	newTunnel, ok := newObj.(*CloudflareTunnel)
	if !ok {
		return nil, fmt.Errorf("new object is not a CloudflareTunnel")
	}

	cloudflaretunnellog.Info("validate update", "name", newTunnel.Name)

	oldTunnel, ok := oldObj.(*CloudflareTunnel)
	if !ok {
		return nil, fmt.Errorf("old object is not a CloudflareTunnel")
	}

	var allErrs field.ErrorList

	// Validate immutable fields
	if newTunnel.Spec.AccountID != oldTunnel.Spec.AccountID {
		allErrs = append(allErrs, field.Forbidden(
			field.NewPath("spec", "accountID"),
			"accountID is immutable after creation",
		))
	}

	// Validate ingress rules if present
	if err := newTunnel.validateIngressRules(); err != nil {
		allErrs = append(allErrs, err...)
	}

	if len(allErrs) == 0 {
		return nil, nil
	}

	return nil, fmt.Errorf("validation failed: %v", allErrs.ToAggregate())
}

// ValidateDelete implements admission.CustomValidator so a webhook will be registered for the type
func (r *CloudflareTunnel) ValidateDelete(ctx context.Context, obj runtime.Object) (admission.Warnings, error) {
	cloudflaretunnellog.Info("validate delete", "name", r.Name)

	// No validation needed for deletion
	return nil, nil
}

// validateIngressRules validates the ingress rules in the CloudflareTunnel spec
func (r *CloudflareTunnel) validateIngressRules() field.ErrorList {
	var allErrs field.ErrorList

	if len(r.Spec.Ingress) == 0 {
		// No ingress rules is valid - tunnel can be configured later
		return nil
	}

	// Track if we have a catch-all rule
	hasCatchAll := false

	for i, rule := range r.Spec.Ingress {
		rulePath := field.NewPath("spec", "ingress").Index(i)

		// Validate hostname format (if provided)
		if rule.Hostname != "" {
			if !isValidHostname(rule.Hostname) {
				allErrs = append(allErrs, field.Invalid(
					rulePath.Child("hostname"),
					rule.Hostname,
					"must be a valid hostname (RFC 1123)",
				))
			}
		} else {
			// Empty hostname means catch-all rule
			if hasCatchAll {
				allErrs = append(allErrs, field.Duplicate(
					rulePath.Child("hostname"),
					"only one catch-all rule (empty hostname) is allowed",
				))
			}
			hasCatchAll = true
		}

		// Validate service URL is required
		if rule.Service == "" {
			allErrs = append(allErrs, field.Required(
				rulePath.Child("service"),
				"service is required",
			))
		} else {
			// Validate service URL format
			if err := validateServiceURL(rule.Service); err != nil {
				allErrs = append(allErrs, field.Invalid(
					rulePath.Child("service"),
					rule.Service,
					err.Error(),
				))
			}
		}
	}

	return allErrs
}

// isValidHostname validates a hostname according to RFC 1123
func isValidHostname(hostname string) bool {
	// Check length (max 253 characters)
	if len(hostname) > 253 || len(hostname) == 0 {
		return false
	}

	// Hostname regex: RFC 1123 compliant
	// - Labels separated by dots
	// - Each label: alphanumeric + hyphens (not at start/end)
	// - Max label length: 63 characters
	hostnameRegex := regexp.MustCompile(`^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$`)
	return hostnameRegex.MatchString(hostname)
}

// validateServiceURL validates the service URL format
func validateServiceURL(service string) error {
	// Check for special cloudflared services
	if strings.HasPrefix(service, "http_status:") {
		// http_status:404, http_status:503, etc.
		return nil
	}

	if strings.HasPrefix(service, "hello_world") || strings.HasPrefix(service, "hello-world") {
		// hello_world service for testing
		return nil
	}

	// Must be a valid URL (http://, https://, unix://, tcp://, etc.)
	validPrefixes := []string{"http://", "https://", "unix://", "tcp://", "ssh://", "rdp://", "smb://"}
	for _, prefix := range validPrefixes {
		if strings.HasPrefix(service, prefix) {
			return nil
		}
	}

	return fmt.Errorf("service must be a valid URL (http://, https://, unix://, tcp://, etc.) or a cloudflared special service (http_status:*, hello_world)")
}
