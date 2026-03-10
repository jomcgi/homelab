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

package controller

import (
	"context"
	"fmt"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	cfclient "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/cloudflare"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// AccessPolicyFinalizerName is the finalizer used by the CloudflareAccessPolicy controller
	AccessPolicyFinalizerName = "cloudflareaccesspolicy.cloudflare.io/finalizer"
)

// CloudflareAccessPolicyReconciler reconciles a CloudflareAccessPolicy object
type CloudflareAccessPolicyReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	tracer trace.Tracer
}

// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflareaccesspolicies,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflareaccesspolicies/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflareaccesspolicies/finalizers,verbs=update
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=httproutes,verbs=get;list;watch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways,verbs=get;list;watch

// Reconcile is part of the main kubernetes reconciliation loop
func (r *CloudflareAccessPolicyReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// Start span for reconciliation
	ctx, span := r.tracer.Start(ctx, "CloudflareAccessPolicy.Reconcile",
		trace.WithAttributes(
			attribute.String("k8s.resource.name", req.Name),
			attribute.String("k8s.resource.namespace", req.Namespace),
		),
	)
	defer span.End()

	log := log.FromContext(ctx)

	// Fetch the CloudflareAccessPolicy instance
	var accessPolicy tunnelsv1.CloudflareAccessPolicy
	if err := r.Get(ctx, req.NamespacedName, &accessPolicy); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("CloudflareAccessPolicy resource not found, ignoring since object must be deleted")
			span.SetStatus(codes.Ok, "resource not found")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get CloudflareAccessPolicy")
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get resource")
		return ctrl.Result{}, err
	}

	span.SetAttributes(
		attribute.String("accesspolicy.name", accessPolicy.Name),
		attribute.String("accesspolicy.namespace", accessPolicy.Namespace),
		attribute.String("accesspolicy.target.kind", accessPolicy.Spec.TargetRef.Kind),
		attribute.String("accesspolicy.target.name", accessPolicy.Spec.TargetRef.Name),
	)

	// Handle deletion
	if accessPolicy.DeletionTimestamp != nil {
		result, err := r.handleDeletion(ctx, &accessPolicy)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "deletion failed")
		} else {
			span.SetStatus(codes.Ok, "resource deleted")
		}
		return result, err
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(&accessPolicy, AccessPolicyFinalizerName) {
		controllerutil.AddFinalizer(&accessPolicy, AccessPolicyFinalizerName)
		span.AddEvent("finalizer added")
		return ctrl.Result{}, r.Update(ctx, &accessPolicy)
	}

	// Handle creation/update
	result, err := r.handleCreateOrUpdate(ctx, &accessPolicy)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "reconciliation failed")
	} else {
		span.SetStatus(codes.Ok, "reconciliation successful")
	}
	return result, err
}

// handleDeletion handles the deletion of a CloudflareAccessPolicy
func (r *CloudflareAccessPolicyReconciler) handleDeletion(ctx context.Context, accessPolicy *tunnelsv1.CloudflareAccessPolicy) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	if !controllerutil.ContainsFinalizer(accessPolicy, AccessPolicyFinalizerName) {
		return ctrl.Result{}, nil
	}

	log.Info("Deleting CloudflareAccessPolicy", "name", accessPolicy.Name, "namespace", accessPolicy.Namespace)

	// Get Cloudflare client
	cfClient, accountID, err := r.getCloudflareClient(ctx, accessPolicy)
	if err != nil {
		log.Error(err, "Failed to get Cloudflare client, skipping cleanup")
		// Continue with finalizer removal even if we can't clean up Cloudflare resources
		controllerutil.RemoveFinalizer(accessPolicy, AccessPolicyFinalizerName)
		return ctrl.Result{}, r.Update(ctx, accessPolicy)
	}

	// Delete access policies
	applicationID := accessPolicy.Status.ApplicationID
	for _, policyID := range accessPolicy.Status.PolicyIDs {
		if err := cfClient.DeleteAccessPolicy(ctx, accountID, applicationID, policyID); err != nil {
			log.Error(err, "Failed to delete access policy", "policyID", policyID)
			// Continue with cleanup even if policy deletion fails
		} else {
			log.V(1).Info("Deleted access policy", "policyID", policyID)
		}
	}

	// Delete access application
	if applicationID != "" {
		if err := cfClient.DeleteAccessApplication(ctx, accountID, applicationID); err != nil {
			log.Error(err, "Failed to delete access application", "applicationID", applicationID)

			// Update status to indicate deletion failure
			meta.SetStatusCondition(&accessPolicy.Status.Conditions, metav1.Condition{
				Type:    tunnelsv1.TypeProgrammed,
				Status:  metav1.ConditionFalse,
				Reason:  tunnelsv1.ReasonCloudflareError,
				Message: fmt.Sprintf("Failed to delete access application: %v", err),
			})
			if err := r.Status().Update(ctx, accessPolicy); err != nil {
				log.Error(err, "Failed to update CloudflareAccessPolicy status")
			}

			// Retry deletion after backoff
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}

		log.V(1).Info("Deleted access application", "applicationID", applicationID)
	}

	// Remove finalizer
	controllerutil.RemoveFinalizer(accessPolicy, AccessPolicyFinalizerName)
	return ctrl.Result{}, r.Update(ctx, accessPolicy)
}

// handleCreateOrUpdate handles the creation or update of a CloudflareAccessPolicy
func (r *CloudflareAccessPolicyReconciler) handleCreateOrUpdate(ctx context.Context, accessPolicy *tunnelsv1.CloudflareAccessPolicy) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Set Accepted condition - policy spec is valid
	meta.SetStatusCondition(&accessPolicy.Status.Conditions, metav1.Condition{
		Type:               tunnelsv1.TypeAccepted,
		Status:             metav1.ConditionTrue,
		Reason:             tunnelsv1.ReasonAccepted,
		Message:            "Policy accepted and attached to target",
		ObservedGeneration: accessPolicy.Generation,
	})

	// Resolve target domain from targetRef
	domain, err := r.resolveTargetDomain(ctx, accessPolicy)
	if err != nil {
		log.Error(err, "Failed to resolve target domain")
		return r.handleError(ctx, accessPolicy, err, "Failed to resolve target")
	}

	// Set ResolvedRefs condition - all references resolved successfully
	meta.SetStatusCondition(&accessPolicy.Status.Conditions, metav1.Condition{
		Type:               tunnelsv1.TypeResolvedRefs,
		Status:             metav1.ConditionTrue,
		Reason:             tunnelsv1.ReasonAccepted,
		Message:            fmt.Sprintf("All references resolved, target domain: %s", domain),
		ObservedGeneration: accessPolicy.Generation,
	})

	// Get Cloudflare client
	cfClient, accountID, err := r.getCloudflareClient(ctx, accessPolicy)
	if err != nil {
		log.Error(err, "Failed to get Cloudflare client")
		return r.handleError(ctx, accessPolicy, err, "Failed to get Cloudflare client")
	}

	// Build access application config
	appConfig := r.buildApplicationConfig(accessPolicy, domain)

	// Create or update access application
	var app *cfclient.AccessApplicationConfig
	if accessPolicy.Status.ApplicationID == "" {
		// Create new application
		app, err = cfClient.CreateAccessApplication(ctx, accountID, appConfig)
		if err != nil {
			log.Error(err, "Failed to create access application")
			return r.handleError(ctx, accessPolicy, err, "Failed to create access application")
		}

		// Update status with application ID
		accessPolicy.Status.ApplicationID = app.ID
		accessPolicy.Status.TargetDomain = domain

		log.Info("Created access application", "applicationID", app.ID, "domain", domain)
	} else {
		// Update existing application
		appConfig.ID = accessPolicy.Status.ApplicationID
		if err := cfClient.UpdateAccessApplication(ctx, accountID, appConfig); err != nil {
			log.Error(err, "Failed to update access application")
			return r.handleError(ctx, accessPolicy, err, "Failed to update access application")
		}

		log.V(1).Info("Updated access application", "applicationID", accessPolicy.Status.ApplicationID)
	}

	// Create or update access policies
	var policyIDs []string
	for i, policy := range accessPolicy.Spec.Policies {
		policyConfig := r.buildPolicyConfig(accessPolicy, policy, i)
		policyConfig.ApplicationID = accessPolicy.Status.ApplicationID

		// Check if we already have this policy
		if i < len(accessPolicy.Status.PolicyIDs) {
			// Update existing policy
			policyConfig.ID = accessPolicy.Status.PolicyIDs[i]
			// Note: Cloudflare doesn't have an UpdateAccessPolicy method in the current API
			// We need to delete and recreate, or skip updating policies
			log.V(1).Info("Policy already exists, skipping update", "policyID", policyConfig.ID)
			policyIDs = append(policyIDs, policyConfig.ID)
		} else {
			// Create new policy
			createdPolicy, err := cfClient.CreateAccessPolicy(ctx, accountID, policyConfig)
			if err != nil {
				log.Error(err, "Failed to create access policy", "policyIndex", i)
				return r.handleError(ctx, accessPolicy, err, "Failed to create access policy")
			}

			policyIDs = append(policyIDs, createdPolicy.ID)
			log.V(1).Info("Created access policy", "policyID", createdPolicy.ID, "decision", policy.Decision)
		}
	}

	// Update status
	accessPolicy.Status.PolicyIDs = policyIDs
	accessPolicy.Status.ObservedGeneration = accessPolicy.Generation

	// Set Programmed condition - policy successfully configured in Cloudflare
	meta.SetStatusCondition(&accessPolicy.Status.Conditions, metav1.Condition{
		Type:               tunnelsv1.TypeProgrammed,
		Status:             metav1.ConditionTrue,
		Reason:             tunnelsv1.ReasonProgrammed,
		Message:            fmt.Sprintf("Access policies programmed for domain %s", domain),
		ObservedGeneration: accessPolicy.Generation,
	})

	if err := r.Status().Update(ctx, accessPolicy); err != nil {
		log.Error(err, "Failed to update CloudflareAccessPolicy status")
		return ctrl.Result{}, err
	}

	log.Info("CloudflareAccessPolicy reconciled successfully",
		"domain", domain,
		"applicationID", accessPolicy.Status.ApplicationID,
		"policyCount", len(policyIDs),
	)

	// Requeue for status check
	return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}

// resolveTargetDomain resolves the domain from the targetRef
func (r *CloudflareAccessPolicyReconciler) resolveTargetDomain(ctx context.Context, accessPolicy *tunnelsv1.CloudflareAccessPolicy) (string, error) {
	targetRef := accessPolicy.Spec.TargetRef

	// Determine namespace (default to policy's namespace if not specified)
	namespace := accessPolicy.Namespace
	if targetRef.Namespace != nil {
		namespace = string(*targetRef.Namespace)
	}

	switch targetRef.Kind {
	case "HTTPRoute":
		// Get HTTPRoute
		var httpRoute gatewayv1.HTTPRoute
		if err := r.Get(ctx, types.NamespacedName{
			Name:      targetRef.Name,
			Namespace: namespace,
		}, &httpRoute); err != nil {
			return "", fmt.Errorf("failed to get HTTPRoute: %w", err)
		}

		// Use first hostname
		if len(httpRoute.Spec.Hostnames) == 0 {
			return "", fmt.Errorf("HTTPRoute has no hostnames")
		}

		return string(httpRoute.Spec.Hostnames[0]), nil

	case "Gateway":
		// Get Gateway
		var gateway gatewayv1.Gateway
		if err := r.Get(ctx, types.NamespacedName{
			Name:      targetRef.Name,
			Namespace: namespace,
		}, &gateway); err != nil {
			return "", fmt.Errorf("failed to get Gateway: %w", err)
		}

		// For Gateway, we need to find all HTTPRoutes that reference it
		// and use the first hostname found
		// For simplicity, we'll use the application domain if specified
		if accessPolicy.Spec.Application.Domain != "" {
			return accessPolicy.Spec.Application.Domain, nil
		}

		return "", fmt.Errorf("Gateway target requires explicit application.domain in spec")

	default:
		return "", fmt.Errorf("unsupported targetRef kind: %s", targetRef.Kind)
	}
}

// buildApplicationConfig builds the Cloudflare Access application config
func (r *CloudflareAccessPolicyReconciler) buildApplicationConfig(accessPolicy *tunnelsv1.CloudflareAccessPolicy, domain string) cfclient.AccessApplicationConfig {
	app := accessPolicy.Spec.Application

	// Default values
	name := app.Name
	if name == "" {
		name = fmt.Sprintf("access-%s-%s", accessPolicy.Namespace, accessPolicy.Name)
	}

	appType := app.Type
	if appType == "" {
		appType = "self_hosted"
	}

	sessionDuration := app.SessionDuration
	if sessionDuration == "" {
		sessionDuration = "24h"
	}

	config := cfclient.AccessApplicationConfig{
		Name:                   name,
		Domain:                 domain,
		Type:                   appType,
		SessionDuration:        sessionDuration,
		AutoRedirectToIdentity: app.AutoRedirectToIdentity,
		EnableBindingCookie:    app.EnableBindingCookie,
		CustomDenyMessage:      app.CustomDenyMessage,
		CustomDenyURL:          app.CustomDenyURL,
	}

	// Add CORS headers if specified
	if app.CORSHeaders != nil {
		corsConfig := cfclient.AccessCORSConfig{
			AllowAllOrigins:  app.CORSHeaders.AllowAllOrigins,
			AllowedOrigins:   app.CORSHeaders.AllowedOrigins,
			AllowedMethods:   app.CORSHeaders.AllowedMethods,
			AllowedHeaders:   app.CORSHeaders.AllowedHeaders,
			AllowCredentials: app.CORSHeaders.AllowCredentials,
		}
		// MaxAge is a pointer in the CRD but a plain int in the client
		if app.CORSHeaders.MaxAge != nil {
			corsConfig.MaxAge = *app.CORSHeaders.MaxAge
		}
		config.CORSHeaders = &corsConfig
	}

	return config
}

// buildPolicyConfig builds the Cloudflare Access policy config
func (r *CloudflareAccessPolicyReconciler) buildPolicyConfig(accessPolicy *tunnelsv1.CloudflareAccessPolicy, policy tunnelsv1.AccessPolicy, index int) cfclient.AccessPolicyConfig {
	// Default values
	name := policy.Name
	if name == "" {
		name = fmt.Sprintf("policy-%d", index)
	}

	decision := policy.Decision
	if decision == "" {
		decision = "allow"
	}

	var includeRules []cfclient.AccessPolicyRule

	// If ExternalPolicyID is set, use it as a group reference instead of inline rules
	if policy.ExternalPolicyID != "" {
		includeRules = []cfclient.AccessPolicyRule{
			{GroupID: policy.ExternalPolicyID},
		}
	} else {
		// Convert rules to Include rules
		// Note: CRD has Name and GitHubUsers fields, but the Cloudflare API client doesn't support them directly
		for _, rule := range policy.Rules {
			cfRule := cfclient.AccessPolicyRule{
				EmailsEndingIn:      rule.EmailsEndingIn,
				Emails:              rule.Emails,
				EmailDomains:        rule.EmailDomains,
				IPRanges:            rule.IPRanges,
				Everyone:            rule.Everyone,
				GitHubOrganizations: rule.GitHubOrganizations, // Use GitHubOrganizations instead of GitHubUsers
				Countries:           rule.Countries,
			}
			includeRules = append(includeRules, cfRule)
		}
	}

	return cfclient.AccessPolicyConfig{
		Name:     name,
		Decision: decision,
		Include:  includeRules, // Rules go into Include
	}
}

// getCloudflareClient creates a Cloudflare API client
func (r *CloudflareAccessPolicyReconciler) getCloudflareClient(ctx context.Context, accessPolicy *tunnelsv1.CloudflareAccessPolicy) (*cfclient.TunnelClient, string, error) {
	// Resolve target to find Gateway
	gateway, err := r.resolveTargetGateway(ctx, accessPolicy)
	if err != nil {
		return nil, "", err
	}

	// Get account ID from Gateway annotations
	accountID := gateway.Annotations[GatewayAnnotationAccountID]
	if accountID == "" {
		return nil, "", fmt.Errorf("Gateway missing account ID annotation")
	}

	// Get GatewayClass to retrieve credentials
	var gatewayClass gatewayv1.GatewayClass
	if err := r.Get(ctx, types.NamespacedName{Name: string(gateway.Spec.GatewayClassName)}, &gatewayClass); err != nil {
		return nil, "", fmt.Errorf("failed to get GatewayClass: %w", err)
	}

	// Get credentials from parametersRef
	if gatewayClass.Spec.ParametersRef == nil {
		return nil, "", fmt.Errorf("GatewayClass has no parametersRef")
	}

	ref := gatewayClass.Spec.ParametersRef
	if ref.Kind != "Secret" || ref.Namespace == nil {
		return nil, "", fmt.Errorf("invalid parametersRef in GatewayClass")
	}

	// Get the credentials Secret
	var secret corev1.Secret
	if err := r.Get(ctx, types.NamespacedName{
		Name:      ref.Name,
		Namespace: string(*ref.Namespace),
	}, &secret); err != nil {
		return nil, "", fmt.Errorf("failed to get credentials secret: %w", err)
	}

	// Extract API token
	apiToken, ok := secret.Data["CLOUDFLARE_API_TOKEN"]
	if !ok {
		return nil, "", fmt.Errorf("credentials secret missing CLOUDFLARE_API_TOKEN")
	}

	// Create Cloudflare client
	cfClient, err := cfclient.NewTunnelClient(string(apiToken))
	if err != nil {
		return nil, "", fmt.Errorf("failed to create Cloudflare client: %w", err)
	}

	return cfClient, accountID, nil
}

// resolveTargetGateway resolves the Gateway from the targetRef
func (r *CloudflareAccessPolicyReconciler) resolveTargetGateway(ctx context.Context, accessPolicy *tunnelsv1.CloudflareAccessPolicy) (*gatewayv1.Gateway, error) {
	targetRef := accessPolicy.Spec.TargetRef

	// Determine namespace
	namespace := accessPolicy.Namespace
	if targetRef.Namespace != nil {
		namespace = string(*targetRef.Namespace)
	}

	switch targetRef.Kind {
	case "Gateway":
		// Get Gateway directly
		var gateway gatewayv1.Gateway
		if err := r.Get(ctx, types.NamespacedName{
			Name:      targetRef.Name,
			Namespace: namespace,
		}, &gateway); err != nil {
			return nil, fmt.Errorf("failed to get Gateway: %w", err)
		}
		return &gateway, nil

	case "HTTPRoute":
		// Get HTTPRoute
		var httpRoute gatewayv1.HTTPRoute
		if err := r.Get(ctx, types.NamespacedName{
			Name:      targetRef.Name,
			Namespace: namespace,
		}, &httpRoute); err != nil {
			return nil, fmt.Errorf("failed to get HTTPRoute: %w", err)
		}

		// Find parent Gateway
		for _, parentRef := range httpRoute.Spec.ParentRefs {
			if parentRef.Kind != nil && *parentRef.Kind != "Gateway" {
				continue
			}

			gatewayNamespace := namespace
			if parentRef.Namespace != nil {
				gatewayNamespace = string(*parentRef.Namespace)
			}

			var gateway gatewayv1.Gateway
			if err := r.Get(ctx, types.NamespacedName{
				Name:      string(parentRef.Name),
				Namespace: gatewayNamespace,
			}, &gateway); err != nil {
				continue
			}

			if gateway.Spec.GatewayClassName == "cloudflare" {
				return &gateway, nil
			}
		}

		return nil, fmt.Errorf("no Cloudflare Gateway found for HTTPRoute")

	default:
		return nil, fmt.Errorf("unsupported targetRef kind: %s", targetRef.Kind)
	}
}

// handleError handles errors and updates status
func (r *CloudflareAccessPolicyReconciler) handleError(ctx context.Context, accessPolicy *tunnelsv1.CloudflareAccessPolicy, err error, message string) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	log.Error(err, message)

	// Set appropriate condition based on error type
	var conditionType, reason string
	switch {
	case message == "Failed to resolve target":
		conditionType = tunnelsv1.TypeResolvedRefs
		reason = tunnelsv1.ReasonTargetNotFound
	case message == "Failed to get Cloudflare client" ||
		message == "Failed to create access application" ||
		message == "Failed to update access application" ||
		message == "Failed to create access policy":
		conditionType = tunnelsv1.TypeProgrammed
		reason = tunnelsv1.ReasonCloudflareError
	default:
		conditionType = tunnelsv1.TypeAccepted
		reason = tunnelsv1.ReasonInvalid
	}

	meta.SetStatusCondition(&accessPolicy.Status.Conditions, metav1.Condition{
		Type:               conditionType,
		Status:             metav1.ConditionFalse,
		Reason:             reason,
		Message:            fmt.Sprintf("%s: %v", message, err),
		ObservedGeneration: accessPolicy.Generation,
	})

	if err := r.Status().Update(ctx, accessPolicy); err != nil {
		log.Error(err, "Failed to update CloudflareAccessPolicy status")
	}

	return ctrl.Result{RequeueAfter: 30 * time.Second}, err
}

// SetupWithManager sets up the controller with the Manager.
func (r *CloudflareAccessPolicyReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("cloudflareaccesspolicy-controller")

	return ctrl.NewControllerManagedBy(mgr).
		For(&tunnelsv1.CloudflareAccessPolicy{}).
		Named("cloudflareaccesspolicy").
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 3,
		}).
		Complete(r)
}
