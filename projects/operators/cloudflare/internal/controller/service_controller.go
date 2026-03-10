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
	"strconv"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// Annotation keys
	AnnotationHostname         = "cloudflare.ingress.hostname"
	AnnotationZeroTrustEnabled = "cloudflare.zero-trust.enabled"
	AnnotationZeroTrustPolicy  = "cloudflare.zero-trust.policy"
	AnnotationServicePort      = "cloudflare.service.port"
)

// getDefaultGatewayName returns the namespace-scoped gateway name
// This ensures one gateway per namespace for traffic isolation
func getDefaultGatewayName(namespace string) string {
	return fmt.Sprintf("namespace-%s", namespace)
}

// ServiceReconciler reconciles a Service object with Cloudflare annotations
type ServiceReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	tracer trace.Tracer
}

// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=httproutes,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflareaccesspolicies,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways,verbs=get;list;watch

// Reconcile is part of the main kubernetes reconciliation loop
func (r *ServiceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// Start span for reconciliation
	ctx, span := r.tracer.Start(ctx, "Service.Reconcile",
		trace.WithAttributes(
			attribute.String("k8s.resource.name", req.Name),
			attribute.String("k8s.resource.namespace", req.Namespace),
		),
	)
	defer span.End()

	log := log.FromContext(ctx)

	// Fetch the Service instance
	var service corev1.Service
	if err := r.Get(ctx, req.NamespacedName, &service); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("Service resource not found, ignoring since object must be deleted")
			span.SetStatus(codes.Ok, "resource not found")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get Service")
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get resource")
		return ctrl.Result{}, err
	}

	// Check if Service has Cloudflare ingress annotation
	hostname, hasAnnotation := service.Annotations[AnnotationHostname]
	if !hasAnnotation || hostname == "" {
		log.V(1).Info("Service does not have cloudflare.ingress.hostname annotation, skipping")
		span.SetStatus(codes.Ok, "no cloudflare annotation")

		// Clean up any existing HTTPRoute/AccessPolicy if annotation was removed
		return r.cleanupResources(ctx, &service)
	}

	span.SetAttributes(
		attribute.String("service.name", service.Name),
		attribute.String("service.namespace", service.Namespace),
		attribute.String("cloudflare.hostname", hostname),
	)

	log.Info("Reconciling Service with Cloudflare annotations", "hostname", hostname)

	// Handle deletion (cleanup happens via owner references)
	if service.DeletionTimestamp != nil {
		log.V(1).Info("Service is being deleted, resources will be cleaned up via owner references")
		span.SetStatus(codes.Ok, "service deleting")
		return ctrl.Result{}, nil
	}

	// Parse annotations
	config := r.parseAnnotations(&service)

	// Ensure Gateway exists
	gatewayName, err := r.ensureGateway(ctx, &service, config)
	if err != nil {
		log.Error(err, "Failed to ensure Gateway exists")
		span.RecordError(err)
		span.SetStatus(codes.Error, "gateway creation failed")
		return ctrl.Result{}, err
	}

	// Create or update HTTPRoute
	if err := r.ensureHTTPRoute(ctx, &service, config, gatewayName); err != nil {
		log.Error(err, "Failed to ensure HTTPRoute")
		span.RecordError(err)
		span.SetStatus(codes.Error, "httproute creation failed")
		return ctrl.Result{}, err
	}

	// Create or update CloudflareAccessPolicy if enabled
	if config.ZeroTrustEnabled {
		if err := r.ensureAccessPolicy(ctx, &service, config); err != nil {
			log.Error(err, "Failed to ensure CloudflareAccessPolicy")
			span.RecordError(err)
			span.SetStatus(codes.Error, "access policy creation failed")
			return ctrl.Result{}, err
		}
	} else {
		// Delete AccessPolicy if it exists but is now disabled
		if err := r.deleteAccessPolicy(ctx, &service); err != nil {
			log.Error(err, "Failed to delete CloudflareAccessPolicy")
			// Continue anyway
		}
	}

	log.Info("Service reconciled successfully",
		"hostname", hostname,
		"gatewayName", gatewayName,
		"zeroTrustEnabled", config.ZeroTrustEnabled,
	)

	span.SetStatus(codes.Ok, "reconciliation successful")
	return ctrl.Result{}, nil
}

// ServiceAnnotationConfig holds parsed Service annotations
type ServiceAnnotationConfig struct {
	Hostname         string
	Port             int32
	ZeroTrustEnabled bool
	ZeroTrustPolicy  string
	GatewayName      string
	GatewayNamespace string
}

// parseAnnotations parses Cloudflare annotations from a Service
func (r *ServiceReconciler) parseAnnotations(service *corev1.Service) ServiceAnnotationConfig {
	config := ServiceAnnotationConfig{
		Hostname:         service.Annotations[AnnotationHostname],
		ZeroTrustEnabled: true, // Default to enabled
	}

	// Parse zero-trust enabled flag
	if enabled, ok := service.Annotations[AnnotationZeroTrustEnabled]; ok {
		config.ZeroTrustEnabled = enabled == "true"
	}

	// Parse zero-trust policy name
	if policy, ok := service.Annotations[AnnotationZeroTrustPolicy]; ok {
		config.ZeroTrustPolicy = policy
	}

	// Parse service port
	if portStr, ok := service.Annotations[AnnotationServicePort]; ok {
		if port, err := strconv.ParseInt(portStr, 10, 32); err == nil {
			config.Port = int32(port)
		}
	}

	// If port not specified, use first port from Service
	if config.Port == 0 && len(service.Spec.Ports) > 0 {
		config.Port = service.Spec.Ports[0].Port
	}

	// Always use namespace-scoped gateway for traffic isolation
	config.GatewayName = getDefaultGatewayName(service.Namespace)
	config.GatewayNamespace = service.Namespace

	return config
}

// ensureGateway ensures the Gateway exists, returns the Gateway name
func (r *ServiceReconciler) ensureGateway(ctx context.Context, service *corev1.Service, config ServiceAnnotationConfig) (string, error) {
	log := log.FromContext(ctx)

	// Check if Gateway exists
	var gateway gatewayv1.Gateway
	err := r.Get(ctx, types.NamespacedName{
		Name:      config.GatewayName,
		Namespace: config.GatewayNamespace,
	}, &gateway)

	if err == nil {
		// Gateway exists, verify it's a Cloudflare Gateway
		if gateway.Spec.GatewayClassName != "cloudflare" {
			return "", fmt.Errorf("Gateway %s/%s exists but is not a Cloudflare Gateway (class: %s)",
				config.GatewayNamespace, config.GatewayName, gateway.Spec.GatewayClassName)
		}
		log.V(1).Info("Using existing Gateway", "gateway", config.GatewayName, "namespace", config.GatewayNamespace)
		return config.GatewayName, nil
	}

	if !errors.IsNotFound(err) {
		return "", fmt.Errorf("failed to get Gateway: %w", err)
	}

	// Gateway doesn't exist - auto-create namespace-scoped gateway
	log.Info("Creating namespace-scoped Cloudflare Gateway", "name", config.GatewayName, "namespace", config.GatewayNamespace)

	// Create namespace-scoped Gateway
	gateway = gatewayv1.Gateway{
		ObjectMeta: metav1.ObjectMeta{
			Name:      config.GatewayName,
			Namespace: config.GatewayNamespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflare-gateway",
				"app.kubernetes.io/managed-by": "cloudflare-operator",
				"cloudflare.io/gateway-scope":  "namespace",
			},
		},
		Spec: gatewayv1.GatewaySpec{
			GatewayClassName: "cloudflare",
			Listeners: []gatewayv1.Listener{
				{
					Name:     "https",
					Protocol: gatewayv1.HTTPSProtocolType,
					Port:     443,
				},
			},
		},
	}

	if err := r.Create(ctx, &gateway); err != nil {
		return "", fmt.Errorf("failed to create Gateway: %w", err)
	}

	log.Info("Created namespace-scoped Cloudflare Gateway successfully", "name", config.GatewayName)
	return config.GatewayName, nil
}

// ensureHTTPRoute creates or updates the HTTPRoute for this Service
func (r *ServiceReconciler) ensureHTTPRoute(ctx context.Context, service *corev1.Service, config ServiceAnnotationConfig, gatewayName string) error {
	log := log.FromContext(ctx)

	routeName := fmt.Sprintf("%s-route", service.Name)

	// Build HTTPRoute
	httpRoute := &gatewayv1.HTTPRoute{
		ObjectMeta: metav1.ObjectMeta{
			Name:      routeName,
			Namespace: service.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflare-httproute",
				"app.kubernetes.io/managed-by": "cloudflare-operator",
				"cloudflare.io/service":        service.Name,
			},
		},
		Spec: gatewayv1.HTTPRouteSpec{
			CommonRouteSpec: gatewayv1.CommonRouteSpec{
				ParentRefs: []gatewayv1.ParentReference{
					{
						Name:      gatewayv1.ObjectName(gatewayName),
						Namespace: ptr.To(gatewayv1.Namespace(config.GatewayNamespace)),
					},
				},
			},
			Hostnames: []gatewayv1.Hostname{
				gatewayv1.Hostname(config.Hostname),
			},
			Rules: []gatewayv1.HTTPRouteRule{
				{
					BackendRefs: []gatewayv1.HTTPBackendRef{
						{
							BackendRef: gatewayv1.BackendRef{
								BackendObjectReference: gatewayv1.BackendObjectReference{
									Name: gatewayv1.ObjectName(service.Name),
									Port: ptr.To(gatewayv1.PortNumber(config.Port)),
								},
							},
						},
					},
				},
			},
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(service, httpRoute, r.Scheme); err != nil {
		return fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if HTTPRoute already exists
	existing := &gatewayv1.HTTPRoute{}
	err := r.Get(ctx, types.NamespacedName{Name: routeName, Namespace: service.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new HTTPRoute
			if err := r.Create(ctx, httpRoute); err != nil {
				return fmt.Errorf("failed to create HTTPRoute: %w", err)
			}
			log.Info("Created HTTPRoute", "name", routeName, "hostname", config.Hostname)
			return nil
		}
		return fmt.Errorf("failed to get HTTPRoute: %w", err)
	}

	// Update existing HTTPRoute
	existing.Spec = httpRoute.Spec
	existing.Labels = httpRoute.Labels
	if err := r.Update(ctx, existing); err != nil {
		return fmt.Errorf("failed to update HTTPRoute: %w", err)
	}

	log.V(1).Info("Updated HTTPRoute", "name", routeName)
	return nil
}

// ensureAccessPolicy creates or updates the CloudflareAccessPolicy for this Service
func (r *ServiceReconciler) ensureAccessPolicy(ctx context.Context, service *corev1.Service, config ServiceAnnotationConfig) error {
	log := log.FromContext(ctx)

	policyName := fmt.Sprintf("%s-access", service.Name)
	routeName := fmt.Sprintf("%s-route", service.Name)

	// Build a simple access policy
	// If a policy name is specified, we assume it references an external policy
	// Otherwise, we create a basic "everyone" policy for demonstration
	var policies []tunnelsv1.AccessPolicy

	if config.ZeroTrustPolicy != "" {
		// Use external policy reference
		policies = []tunnelsv1.AccessPolicy{
			{
				Name:             config.ZeroTrustPolicy,
				ExternalPolicyID: config.ZeroTrustPolicy,
				Decision:         "allow",
				Rules: []tunnelsv1.AccessPolicyRule{
					{
						Name:     "external-policy",
						Everyone: true, // Placeholder, actual rules come from external policy
					},
				},
			},
		}
	} else {
		// Create a default policy (everyone allowed - should be customized)
		policies = []tunnelsv1.AccessPolicy{
			{
				Name:     "default-allow",
				Decision: "allow",
				Rules: []tunnelsv1.AccessPolicyRule{
					{
						Name:     "allow-all",
						Everyone: true,
					},
				},
			},
		}
	}

	accessPolicy := &tunnelsv1.CloudflareAccessPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      policyName,
			Namespace: service.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflare-access-policy",
				"app.kubernetes.io/managed-by": "cloudflare-operator",
				"cloudflare.io/service":        service.Name,
			},
		},
		Spec: tunnelsv1.CloudflareAccessPolicySpec{
			TargetRef: tunnelsv1.PolicyTargetReference{
				Group: "gateway.networking.k8s.io",
				Kind:  "HTTPRoute",
				Name:  routeName,
			},
			Application: tunnelsv1.ApplicationConfig{
				Name:            fmt.Sprintf("%s (%s)", service.Name, service.Namespace),
				SessionDuration: "24h",
				Type:            "self_hosted",
			},
			Policies: policies,
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(service, accessPolicy, r.Scheme); err != nil {
		return fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if AccessPolicy already exists
	existing := &tunnelsv1.CloudflareAccessPolicy{}
	err := r.Get(ctx, types.NamespacedName{Name: policyName, Namespace: service.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new AccessPolicy
			if err := r.Create(ctx, accessPolicy); err != nil {
				return fmt.Errorf("failed to create CloudflareAccessPolicy: %w", err)
			}
			log.Info("Created CloudflareAccessPolicy", "name", policyName)
			return nil
		}
		return fmt.Errorf("failed to get CloudflareAccessPolicy: %w", err)
	}

	// Update existing AccessPolicy
	existing.Spec = accessPolicy.Spec
	existing.Labels = accessPolicy.Labels
	if err := r.Update(ctx, existing); err != nil {
		return fmt.Errorf("failed to update CloudflareAccessPolicy: %w", err)
	}

	log.V(1).Info("Updated CloudflareAccessPolicy", "name", policyName)
	return nil
}

// deleteAccessPolicy deletes the CloudflareAccessPolicy if it exists
func (r *ServiceReconciler) deleteAccessPolicy(ctx context.Context, service *corev1.Service) error {
	policyName := fmt.Sprintf("%s-access", service.Name)

	accessPolicy := &tunnelsv1.CloudflareAccessPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      policyName,
			Namespace: service.Namespace,
		},
	}

	err := r.Delete(ctx, accessPolicy)
	if err != nil && !errors.IsNotFound(err) {
		return fmt.Errorf("failed to delete CloudflareAccessPolicy: %w", err)
	}

	return nil
}

// cleanupResources removes HTTPRoute and AccessPolicy when annotation is removed
func (r *ServiceReconciler) cleanupResources(ctx context.Context, service *corev1.Service) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	routeName := fmt.Sprintf("%s-route", service.Name)
	policyName := fmt.Sprintf("%s-access", service.Name)

	// Delete HTTPRoute
	httpRoute := &gatewayv1.HTTPRoute{
		ObjectMeta: metav1.ObjectMeta{
			Name:      routeName,
			Namespace: service.Namespace,
		},
	}
	if err := r.Delete(ctx, httpRoute); err != nil && !errors.IsNotFound(err) {
		log.Error(err, "Failed to delete HTTPRoute")
		return ctrl.Result{}, err
	}

	// Delete AccessPolicy
	accessPolicy := &tunnelsv1.CloudflareAccessPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      policyName,
			Namespace: service.Namespace,
		},
	}
	if err := r.Delete(ctx, accessPolicy); err != nil && !errors.IsNotFound(err) {
		log.Error(err, "Failed to delete CloudflareAccessPolicy")
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *ServiceReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("service-controller")

	return ctrl.NewControllerManagedBy(mgr).
		For(&corev1.Service{}).
		Owns(&gatewayv1.HTTPRoute{}).
		Owns(&tunnelsv1.CloudflareAccessPolicy{}).
		Named("service").
		Complete(r)
}
