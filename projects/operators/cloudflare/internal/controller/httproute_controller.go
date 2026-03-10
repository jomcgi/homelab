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
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	cfclient "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/cloudflare"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// HTTPRouteFinalizerName is the finalizer used by the HTTPRoute controller
	HTTPRouteFinalizerName = "httproute.cloudflare.io/finalizer"

	// HTTPRouteAnnotationDNSRecordID stores the DNS record ID for cleanup
	HTTPRouteAnnotationDNSRecordIDPrefix = "httproute.cloudflare.io/dns-record-id."

	// HTTPRouteAnnotationZoneID stores the Cloudflare zone ID
	HTTPRouteAnnotationZoneIDPrefix = "httproute.cloudflare.io/zone-id."
)

// HTTPRouteReconciler reconciles a HTTPRoute object
type HTTPRouteReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	tracer trace.Tracer
}

// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=httproutes,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=httproutes/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=httproutes/finalizers,verbs=update
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch

// Reconcile is part of the main kubernetes reconciliation loop
func (r *HTTPRouteReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// Start span for reconciliation
	ctx, span := r.tracer.Start(ctx, "HTTPRoute.Reconcile",
		trace.WithAttributes(
			attribute.String("k8s.resource.name", req.Name),
			attribute.String("k8s.resource.namespace", req.Namespace),
		),
	)
	defer span.End()

	log := log.FromContext(ctx)

	// Fetch the HTTPRoute instance
	var httpRoute gatewayv1.HTTPRoute
	if err := r.Get(ctx, req.NamespacedName, &httpRoute); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("HTTPRoute resource not found, ignoring since object must be deleted")
			span.SetStatus(codes.Ok, "resource not found")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get HTTPRoute")
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get resource")
		return ctrl.Result{}, err
	}

	span.SetAttributes(
		attribute.String("httproute.name", httpRoute.Name),
		attribute.String("httproute.namespace", httpRoute.Namespace),
	)

	// Handle deletion
	if httpRoute.DeletionTimestamp != nil {
		result, err := r.handleDeletion(ctx, &httpRoute)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "deletion failed")
		} else {
			span.SetStatus(codes.Ok, "resource deleted")
		}
		return result, err
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(&httpRoute, HTTPRouteFinalizerName) {
		controllerutil.AddFinalizer(&httpRoute, HTTPRouteFinalizerName)
		span.AddEvent("finalizer added")
		return ctrl.Result{}, r.Update(ctx, &httpRoute)
	}

	// Handle creation/update
	result, err := r.handleCreateOrUpdate(ctx, &httpRoute)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "reconciliation failed")
	} else {
		span.SetStatus(codes.Ok, "reconciliation successful")
	}
	return result, err
}

// handleDeletion handles the deletion of an HTTPRoute
func (r *HTTPRouteReconciler) handleDeletion(ctx context.Context, httpRoute *gatewayv1.HTTPRoute) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	if !controllerutil.ContainsFinalizer(httpRoute, HTTPRouteFinalizerName) {
		return ctrl.Result{}, nil
	}

	log.Info("Deleting HTTPRoute", "name", httpRoute.Name, "namespace", httpRoute.Namespace)

	// Get Gateway and Cloudflare client
	gateway, cfClient, accountID, tunnelID, err := r.getGatewayAndClient(ctx, httpRoute)
	if err != nil {
		log.Error(err, "Failed to get Gateway and Cloudflare client, skipping cleanup")
		// Continue with finalizer removal even if we can't clean up Cloudflare resources
		controllerutil.RemoveFinalizer(httpRoute, HTTPRouteFinalizerName)
		return ctrl.Result{}, r.Update(ctx, httpRoute)
	}

	// Delete DNS records and published routes for each hostname
	for _, hostname := range httpRoute.Spec.Hostnames {
		hostnameStr := string(hostname)
		log.V(1).Info("Cleaning up hostname", "hostname", hostnameStr)

		// Delete DNS record
		dnsRecordIDKey := fmt.Sprintf("%s%s", HTTPRouteAnnotationDNSRecordIDPrefix, hostnameStr)
		zoneIDKey := fmt.Sprintf("%s%s", HTTPRouteAnnotationZoneIDPrefix, hostnameStr)

		if dnsRecordID, ok := httpRoute.Annotations[dnsRecordIDKey]; ok && dnsRecordID != "" {
			if zoneID, ok := httpRoute.Annotations[zoneIDKey]; ok && zoneID != "" {
				if err := cfClient.DeleteDNSRecord(ctx, zoneID, dnsRecordID); err != nil {
					log.Error(err, "Failed to delete DNS record", "hostname", hostnameStr, "recordID", dnsRecordID)
					// Continue with cleanup even if DNS deletion fails
				} else {
					log.V(1).Info("Deleted DNS record", "hostname", hostnameStr, "recordID", dnsRecordID)
				}
			}
		}

		// Delete published route
		if err := cfClient.DeletePublishedRoute(ctx, accountID, tunnelID, hostnameStr); err != nil {
			log.Error(err, "Failed to delete published route", "hostname", hostnameStr)
			// Continue with cleanup even if route deletion fails
		} else {
			log.V(1).Info("Deleted published route", "hostname", hostnameStr)
		}
	}

	// Remove finalizer
	controllerutil.RemoveFinalizer(httpRoute, HTTPRouteFinalizerName)
	_ = gateway // Suppress unused warning
	return ctrl.Result{}, r.Update(ctx, httpRoute)
}

// handleCreateOrUpdate handles the creation or update of an HTTPRoute
func (r *HTTPRouteReconciler) handleCreateOrUpdate(ctx context.Context, httpRoute *gatewayv1.HTTPRoute) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Get Gateway and Cloudflare client
	gateway, cfClient, accountID, tunnelID, err := r.getGatewayAndClient(ctx, httpRoute)
	if err != nil {
		log.Error(err, "Failed to get Gateway and Cloudflare client")
		return r.handleError(ctx, httpRoute, err, "Failed to get Gateway")
	}

	// Ensure annotations map exists
	if httpRoute.Annotations == nil {
		httpRoute.Annotations = make(map[string]string)
	}

	// Process each hostname in the HTTPRoute
	allSuccessful := true
	var routeErrors []error

	for _, hostname := range httpRoute.Spec.Hostnames {
		hostnameStr := string(hostname)
		log.V(1).Info("Processing hostname", "hostname", hostnameStr)

		// Build backend service URL from backendRefs
		serviceURL, err := r.getBackendServiceURL(ctx, httpRoute)
		if err != nil {
			log.Error(err, "Failed to resolve backend service", "hostname", hostnameStr)
			allSuccessful = false
			routeErrors = append(routeErrors, err)
			continue
		}

		// Create or update published route in Cloudflare tunnel configuration
		route := cfclient.RouteConfig{
			Hostname: hostnameStr,
			Service:  serviceURL,
		}

		if err := cfClient.CreatePublishedRoute(ctx, accountID, tunnelID, route); err != nil {
			log.Error(err, "Failed to create published route", "hostname", hostnameStr)
			allSuccessful = false
			routeErrors = append(routeErrors, err)
			continue
		}

		log.V(1).Info("Created/updated published route", "hostname", hostnameStr, "service", serviceURL)

		// Ensure DNS CNAME record pointing to the tunnel
		expectedTarget := fmt.Sprintf("%s.cfargotunnel.com", tunnelID)
		var dnsRecord *cfclient.DNSRecordConfig

		// Check if DNS record already exists
		existingRecord, err := cfClient.GetDNSRecordByName(ctx, hostnameStr)
		if err == nil {
			// Record exists - validate it matches our expectations
			if existingRecord.Type == "CNAME" && existingRecord.Content == expectedTarget {
				// Record matches - adopt it
				log.V(1).Info("Adopting existing DNS record",
					"hostname", hostnameStr,
					"recordID", existingRecord.RecordID,
					"target", existingRecord.Content,
				)
				dnsRecord = existingRecord
			} else {
				// Record exists but doesn't match - error
				err := fmt.Errorf("existing DNS record does not match expected configuration: type=%s (expected CNAME), target=%s (expected %s)",
					existingRecord.Type, existingRecord.Content, expectedTarget)
				log.Error(err, "DNS record mismatch", "hostname", hostnameStr)
				allSuccessful = false
				routeErrors = append(routeErrors, err)
				continue
			}
		} else {
			// Record doesn't exist - create it
			log.V(1).Info("Creating new DNS record", "hostname", hostnameStr, "target", expectedTarget)
			dnsRecord, err = cfClient.CreateTunnelDNSRecord(ctx, hostnameStr, tunnelID)
			if err != nil {
				log.Error(err, "Failed to create DNS record", "hostname", hostnameStr)
				allSuccessful = false
				routeErrors = append(routeErrors, err)
				continue
			}
			log.V(1).Info("Created DNS record",
				"hostname", hostnameStr,
				"recordID", dnsRecord.RecordID,
				"target", dnsRecord.Content,
			)
		}

		// Store DNS record ID and zone ID in annotations for cleanup
		dnsRecordIDKey := fmt.Sprintf("%s%s", HTTPRouteAnnotationDNSRecordIDPrefix, hostnameStr)
		zoneIDKey := fmt.Sprintf("%s%s", HTTPRouteAnnotationZoneIDPrefix, hostnameStr)
		httpRoute.Annotations[dnsRecordIDKey] = dnsRecord.RecordID
		httpRoute.Annotations[zoneIDKey] = dnsRecord.ZoneID
	}

	// Update HTTPRoute annotations
	if err := r.Update(ctx, httpRoute); err != nil {
		log.Error(err, "Failed to update HTTPRoute annotations")
		return ctrl.Result{}, err
	}

	// Update HTTPRoute status
	if allSuccessful {
		return r.setRouteStatus(ctx, httpRoute, gateway, true, "Programmed", "Route is programmed in Cloudflare")
	} else {
		return r.setRouteStatus(ctx, httpRoute, gateway, false, "PartiallyProgrammed",
			fmt.Sprintf("Some hostnames failed to program: %v", routeErrors))
	}
}

// getGatewayAndClient retrieves the parent Gateway and creates a Cloudflare API client
func (r *HTTPRouteReconciler) getGatewayAndClient(ctx context.Context, httpRoute *gatewayv1.HTTPRoute) (*gatewayv1.Gateway, *cfclient.TunnelClient, string, string, error) {
	// Find the parent Gateway from parentRefs
	var gateway gatewayv1.Gateway
	var foundGateway bool

	for _, parentRef := range httpRoute.Spec.ParentRefs {
		// Default to Gateway kind if not specified
		if parentRef.Kind != nil && *parentRef.Kind != "Gateway" {
			continue
		}

		// Determine namespace (default to HTTPRoute's namespace if not specified)
		namespace := httpRoute.Namespace
		if parentRef.Namespace != nil {
			namespace = string(*parentRef.Namespace)
		}

		// Get the Gateway
		if err := r.Get(ctx, types.NamespacedName{
			Name:      string(parentRef.Name),
			Namespace: namespace,
		}, &gateway); err != nil {
			if errors.IsNotFound(err) {
				continue
			}
			return nil, nil, "", "", fmt.Errorf("failed to get Gateway: %w", err)
		}

		// Check if this is a Cloudflare Gateway
		if gateway.Spec.GatewayClassName != "cloudflare" {
			continue
		}

		foundGateway = true
		break
	}

	if !foundGateway {
		return nil, nil, "", "", fmt.Errorf("no Cloudflare Gateway found in parentRefs")
	}

	// Get tunnel ID and account ID from Gateway annotations
	tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]
	accountID := gateway.Annotations[GatewayAnnotationAccountID]

	if tunnelID == "" || accountID == "" {
		return nil, nil, "", "", fmt.Errorf("Gateway missing tunnel metadata (tunnel ID or account ID)")
	}

	// Get GatewayClass to retrieve credentials
	var gatewayClass gatewayv1.GatewayClass
	if err := r.Get(ctx, types.NamespacedName{Name: string(gateway.Spec.GatewayClassName)}, &gatewayClass); err != nil {
		return nil, nil, "", "", fmt.Errorf("failed to get GatewayClass: %w", err)
	}

	// Get credentials from parametersRef
	if gatewayClass.Spec.ParametersRef == nil {
		return nil, nil, "", "", fmt.Errorf("GatewayClass has no parametersRef")
	}

	ref := gatewayClass.Spec.ParametersRef
	if ref.Kind != "Secret" || ref.Namespace == nil {
		return nil, nil, "", "", fmt.Errorf("invalid parametersRef in GatewayClass")
	}

	// Get the credentials Secret
	var secret corev1.Secret
	if err := r.Get(ctx, types.NamespacedName{
		Name:      ref.Name,
		Namespace: string(*ref.Namespace),
	}, &secret); err != nil {
		return nil, nil, "", "", fmt.Errorf("failed to get credentials secret: %w", err)
	}

	// Extract API token
	apiToken, ok := secret.Data["CLOUDFLARE_API_TOKEN"]
	if !ok {
		return nil, nil, "", "", fmt.Errorf("credentials secret missing CLOUDFLARE_API_TOKEN")
	}

	// Create Cloudflare client
	cfClient, err := cfclient.NewTunnelClient(string(apiToken))
	if err != nil {
		return nil, nil, "", "", fmt.Errorf("failed to create Cloudflare client: %w", err)
	}

	return &gateway, cfClient, accountID, tunnelID, nil
}

// getBackendServiceURL constructs the backend service URL from HTTPRoute backendRefs
func (r *HTTPRouteReconciler) getBackendServiceURL(ctx context.Context, httpRoute *gatewayv1.HTTPRoute) (string, error) {
	// Get the first rule (we'll support only one rule for now)
	if len(httpRoute.Spec.Rules) == 0 {
		return "", fmt.Errorf("HTTPRoute has no rules")
	}

	rule := httpRoute.Spec.Rules[0]
	if len(rule.BackendRefs) == 0 {
		return "", fmt.Errorf("HTTPRoute rule has no backendRefs")
	}

	backendRef := rule.BackendRefs[0]

	// Default to Service kind if not specified
	if backendRef.Kind != nil && *backendRef.Kind != "Service" {
		return "", fmt.Errorf("unsupported backendRef kind: %v", *backendRef.Kind)
	}

	// Determine namespace (default to HTTPRoute's namespace if not specified)
	namespace := httpRoute.Namespace
	if backendRef.Namespace != nil {
		namespace = string(*backendRef.Namespace)
	}

	// Get the Service
	var service corev1.Service
	if err := r.Get(ctx, types.NamespacedName{
		Name:      string(backendRef.Name),
		Namespace: namespace,
	}, &service); err != nil {
		return "", fmt.Errorf("failed to get backend Service: %w", err)
	}

	// Determine port
	var port int32
	if backendRef.Port != nil {
		port = int32(*backendRef.Port)
	} else if len(service.Spec.Ports) > 0 {
		port = service.Spec.Ports[0].Port
	} else {
		return "", fmt.Errorf("no port specified in backendRef and Service has no ports")
	}

	// Construct service URL (http://service-name.namespace.svc:port)
	// This assumes the Service is in the same cluster as cloudflared
	serviceURL := fmt.Sprintf("http://%s.%s.svc:%d", service.Name, service.Namespace, port)

	return serviceURL, nil
}

// setRouteStatus updates the HTTPRoute status with parent status
func (r *HTTPRouteReconciler) setRouteStatus(ctx context.Context, httpRoute *gatewayv1.HTTPRoute, gateway *gatewayv1.Gateway, accepted bool, reason, message string) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Build parent status
	parentStatus := gatewayv1.RouteParentStatus{
		ParentRef: gatewayv1.ParentReference{
			Name:      gatewayv1.ObjectName(gateway.Name),
			Namespace: ptr.To(gatewayv1.Namespace(gateway.Namespace)),
		},
		ControllerName: ControllerName,
		Conditions:     []metav1.Condition{},
	}

	// Set Accepted condition
	if accepted {
		meta.SetStatusCondition(&parentStatus.Conditions, metav1.Condition{
			Type:               string(gatewayv1.RouteConditionAccepted),
			Status:             metav1.ConditionTrue,
			Reason:             reason,
			Message:            message,
			ObservedGeneration: httpRoute.Generation,
		})

		meta.SetStatusCondition(&parentStatus.Conditions, metav1.Condition{
			Type:               string(gatewayv1.RouteConditionResolvedRefs),
			Status:             metav1.ConditionTrue,
			Reason:             "ResolvedRefs",
			Message:            "All references resolved",
			ObservedGeneration: httpRoute.Generation,
		})
	} else {
		meta.SetStatusCondition(&parentStatus.Conditions, metav1.Condition{
			Type:               string(gatewayv1.RouteConditionAccepted),
			Status:             metav1.ConditionFalse,
			Reason:             reason,
			Message:            message,
			ObservedGeneration: httpRoute.Generation,
		})
	}

	// Update route parent status
	httpRoute.Status.RouteStatus.Parents = []gatewayv1.RouteParentStatus{parentStatus}

	if err := r.Status().Update(ctx, httpRoute); err != nil {
		log.Error(err, "Failed to update HTTPRoute status")
		return ctrl.Result{}, err
	}

	// Requeue for status check
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

// handleError handles errors and updates HTTPRoute status
func (r *HTTPRouteReconciler) handleError(ctx context.Context, httpRoute *gatewayv1.HTTPRoute, err error, message string) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	log.Error(err, message)

	// Try to update status to reflect the error
	// If we can't find the Gateway, use a minimal parent status
	parentStatus := gatewayv1.RouteParentStatus{
		ControllerName: ControllerName,
		Conditions: []metav1.Condition{
			{
				Type:               string(gatewayv1.RouteConditionAccepted),
				Status:             metav1.ConditionFalse,
				Reason:             "GatewayNotFound",
				Message:            fmt.Sprintf("%s: %v", message, err),
				ObservedGeneration: httpRoute.Generation,
			},
		},
	}

	httpRoute.Status.RouteStatus.Parents = []gatewayv1.RouteParentStatus{parentStatus}

	if err := r.Status().Update(ctx, httpRoute); err != nil {
		log.Error(err, "Failed to update HTTPRoute status")
	}

	return ctrl.Result{RequeueAfter: 30 * time.Second}, err
}

// SetupWithManager sets up the controller with the Manager.
func (r *HTTPRouteReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("httproute-controller")

	return ctrl.NewControllerManagedBy(mgr).
		For(&gatewayv1.HTTPRoute{}).
		Named("httproute").
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 3,
		}).
		Complete(r)
}
