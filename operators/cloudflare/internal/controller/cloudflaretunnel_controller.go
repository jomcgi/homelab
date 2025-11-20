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
	goerrors "errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/cloudflare/cloudflare-go"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	tunnelsv1 "github.com/jomcgi/homelab/operators/cloudflare/api/v1"
	cfclient "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
	"github.com/jomcgi/homelab/operators/cloudflare/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// FinalizerName is the finalizer used by this controller
	FinalizerName = "tunnels.cloudflare.io/finalizer"
)

// CloudflareTunnelReconciler reconciles a CloudflareTunnel object
type CloudflareTunnelReconciler struct {
	client.Client
	Scheme   *runtime.Scheme
	CFClient cfclient.TunnelClientInterface
	tracer   trace.Tracer
}

// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflaretunnels,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflaretunnels/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=tunnels.cloudflare.io,resources=cloudflaretunnels/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
func (r *CloudflareTunnelReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// Start span for reconciliation
	ctx, span := r.tracer.Start(ctx, "Reconcile",
		trace.WithAttributes(
			attribute.String("k8s.resource.name", req.Name),
			attribute.String("k8s.resource.namespace", req.Namespace),
		),
	)
	defer span.End()

	log := logf.FromContext(ctx)

	// Fetch the CloudflareTunnel instance
	var tunnel tunnelsv1.CloudflareTunnel
	if err := r.Get(ctx, req.NamespacedName, &tunnel); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("CloudflareTunnel resource not found, ignoring since object must be deleted")
			span.SetStatus(codes.Ok, "resource not found")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get CloudflareTunnel")
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get resource")
		return ctrl.Result{}, err
	}

	// Add resource information to span
	span.SetAttributes(
		attribute.String("tunnel.name", tunnel.Spec.Name),
		attribute.String("tunnel.id", tunnel.Status.TunnelID),
		attribute.String("account.id", tunnel.Spec.AccountID),
	)

	// Skip reconciliation if spec hasn't changed (generation-based reconciliation)
	// This prevents unnecessary API calls to Cloudflare on status-only updates
	if tunnel.Generation == tunnel.Status.ObservedGeneration && tunnel.DeletionTimestamp == nil {
		log.V(1).Info("Skipping reconciliation - no spec changes detected",
			"generation", tunnel.Generation,
			"observedGeneration", tunnel.Status.ObservedGeneration)
		span.AddEvent("skipped - no spec changes")
		span.SetStatus(codes.Ok, "no changes")
		// Still requeue for periodic status checks
		return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
	}

	// Handle deletion
	if tunnel.DeletionTimestamp != nil {
		result, err := r.handleDeletion(ctx, &tunnel)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "deletion failed")
		} else {
			span.SetStatus(codes.Ok, "resource deleted")
		}
		return result, err
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(&tunnel, FinalizerName) {
		controllerutil.AddFinalizer(&tunnel, FinalizerName)
		span.AddEvent("finalizer added")
		return ctrl.Result{}, r.Update(ctx, &tunnel)
	}

	// Handle creation/update
	result, err := r.handleCreateOrUpdate(ctx, &tunnel)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "reconciliation failed")
	} else {
		span.SetStatus(codes.Ok, "reconciliation successful")
	}
	return result, err
}

// handleDeletion handles the deletion of a CloudflareTunnel
func (r *CloudflareTunnelReconciler) handleDeletion(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	if !controllerutil.ContainsFinalizer(tunnel, FinalizerName) {
		return ctrl.Result{}, nil
	}

	log.Info("Deleting CloudflareTunnel", "tunnel", tunnel.Name, "tunnelID", tunnel.Status.TunnelID)

	// Delete tunnel from Cloudflare if it exists
	if tunnel.Status.TunnelID != "" {
		err := r.CFClient.DeleteTunnel(ctx, tunnel.Spec.AccountID, tunnel.Status.TunnelID)
		if err != nil && !cfclient.IsNotFoundError(err) {
			log.Error(err, "Failed to delete tunnel from Cloudflare")

			// Update status to indicate deletion failure
			meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
				Type:    tunnelsv1.TypeDegraded,
				Status:  metav1.ConditionTrue,
				Reason:  tunnelsv1.ReasonAPIError,
				Message: fmt.Sprintf("Failed to delete tunnel: %v", err),
			})
			if err := r.Status().Update(ctx, tunnel); err != nil {
				log.Error(err, "Failed to update tunnel status")
			}

			// Retry deletion after backoff
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}
	}

	// Remove finalizer
	controllerutil.RemoveFinalizer(tunnel, FinalizerName)
	return ctrl.Result{}, r.Update(ctx, tunnel)
}

// handleCreateOrUpdate handles the creation or update of a CloudflareTunnel
func (r *CloudflareTunnelReconciler) handleCreateOrUpdate(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) (ctrl.Result, error) {
	// Update observed generation
	tunnel.Status.ObservedGeneration = tunnel.Generation

	// Create tunnel if it doesn't exist
	if tunnel.Status.TunnelID == "" {
		return r.createTunnel(ctx, tunnel)
	}

	// Update tunnel status
	return r.updateTunnelStatus(ctx, tunnel)
}

// createTunnel creates a new tunnel in Cloudflare
func (r *CloudflareTunnelReconciler) createTunnel(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	// Auto-generate unique tunnel name if not specified
	tunnelName := tunnel.Spec.Name
	if tunnelName == "" {
		// Use CRD name + short UID prefix for globally unique name
		// Format: {crd-name}-{first-8-chars-of-uid}
		uidPrefix := string(tunnel.UID)[:8]
		tunnelName = fmt.Sprintf("%s-%s", tunnel.Name, uidPrefix)
		log.Info("Auto-generating unique tunnel name", "tunnelName", tunnelName)
	}

	log.Info("Creating CloudflareTunnel", "tunnel", tunnelName, "account", tunnel.Spec.AccountID)

	// Set progressing condition
	meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
		Type:    tunnelsv1.TypeProgressing,
		Status:  metav1.ConditionTrue,
		Reason:  tunnelsv1.ReasonCreating,
		Message: "Creating tunnel in Cloudflare",
	})

	if err := r.Status().Update(ctx, tunnel); err != nil {
		return ctrl.Result{}, err
	}

	// Create tunnel via Cloudflare API
	cfTunnel, _, err := r.CFClient.CreateTunnel(ctx, tunnel.Spec.AccountID, tunnelName)
	if err != nil {
		// Check if the error is because tunnel name already exists (code 1013)
		if strings.Contains(err.Error(), "(1013)") || strings.Contains(err.Error(), "already have a tunnel with this name") {
			log.Info("Tunnel name already exists, attempting to adopt existing tunnel", "tunnelName", tunnelName)

			// List all tunnels to find the one with this name
			tunnels, listErr := r.CFClient.ListTunnels(ctx, tunnel.Spec.AccountID)
			if listErr != nil {
				log.Error(listErr, "Failed to list tunnels for adoption")
				meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
					Type:    tunnelsv1.TypeDegraded,
					Status:  metav1.ConditionTrue,
					Reason:  tunnelsv1.ReasonAPIError,
					Message: fmt.Sprintf("Failed to adopt tunnel: %v", listErr),
				})
				if err := r.Status().Update(ctx, tunnel); err != nil {
					log.Error(err, "Failed to update tunnel status")
				}
				return r.handleAPIError(listErr)
			}

			// Find the tunnel with the matching name
			var existingTunnel *cloudflare.Tunnel
			for i := range tunnels {
				if tunnels[i].Name == tunnelName {
					existingTunnel = &tunnels[i]
					break
				}
			}

			if existingTunnel == nil {
				log.Error(fmt.Errorf("tunnel not found"), "Tunnel name exists but not found in list", "tunnelName", tunnelName)
				meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
					Type:    tunnelsv1.TypeDegraded,
					Status:  metav1.ConditionTrue,
					Reason:  tunnelsv1.ReasonAPIError,
					Message: fmt.Sprintf("Tunnel name exists but not found: %s", tunnelName),
				})
				if err := r.Status().Update(ctx, tunnel); err != nil {
					log.Error(err, "Failed to update tunnel status")
				}
				return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
			}

			log.Info("Successfully adopted existing tunnel", "tunnelName", tunnelName, "tunnelID", existingTunnel.ID)
			cfTunnel = existingTunnel
			// Note: Tunnel secret/token will be retrieved via GetTunnelToken below regardless of create vs adopt
		} else {
			// Different error, handle as before
			log.Error(err, "Failed to create tunnel")
			meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
				Type:    tunnelsv1.TypeDegraded,
				Status:  metav1.ConditionTrue,
				Reason:  tunnelsv1.ReasonAPIError,
				Message: fmt.Sprintf("Failed to create tunnel: %v", err),
			})
			if err := r.Status().Update(ctx, tunnel); err != nil {
				log.Error(err, "Failed to update tunnel status")
			}
			return r.handleAPIError(err)
		}
	}

	// Update status with tunnel ID
	tunnel.Status.TunnelID = cfTunnel.ID
	tunnel.Status.Ready = true

	// Set ready condition
	meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
		Type:    tunnelsv1.TypeReady,
		Status:  metav1.ConditionTrue,
		Reason:  "TunnelCreated",
		Message: fmt.Sprintf("Tunnel %s created successfully", cfTunnel.ID),
	})

	// Remove progressing condition
	meta.RemoveStatusCondition(&tunnel.Status.Conditions, tunnelsv1.TypeProgressing)

	if err := r.Status().Update(ctx, tunnel); err != nil {
		return ctrl.Result{}, err
	}

	log.Info("CloudflareTunnel created successfully", "tunnelID", cfTunnel.ID)

	// Update tunnel configuration if ingress rules are specified
	if len(tunnel.Spec.Ingress) > 0 {
		return r.updateTunnelConfiguration(ctx, tunnel)
	}

	// Schedule status check
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

// updateTunnelStatus updates the tunnel status from Cloudflare
func (r *CloudflareTunnelReconciler) updateTunnelStatus(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	// Get tunnel status from Cloudflare
	cfTunnel, err := r.CFClient.GetTunnel(ctx, tunnel.Spec.AccountID, tunnel.Status.TunnelID)
	if err != nil {
		if cfclient.IsNotFoundError(err) {
			log.Info("Tunnel not found in Cloudflare, recreating", "tunnelID", tunnel.Status.TunnelID)
			tunnel.Status.TunnelID = ""
			tunnel.Status.Ready = false
			tunnel.Status.Active = false
			return r.createTunnel(ctx, tunnel)
		}

		log.Error(err, "Failed to get tunnel status")
		meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
			Type:    tunnelsv1.TypeDegraded,
			Status:  metav1.ConditionTrue,
			Reason:  tunnelsv1.ReasonAPIError,
			Message: fmt.Sprintf("Failed to get tunnel status: %v", err),
		})

		if err := r.Status().Update(ctx, tunnel); err != nil {
			log.Error(err, "Failed to update tunnel status")
		}
		return r.handleAPIError(err)
	}

	// Update active status based on tunnel connections
	hasConnections := len(cfTunnel.Connections) > 0
	tunnel.Status.Active = hasConnections

	if hasConnections {
		meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
			Type:    tunnelsv1.TypeActive,
			Status:  metav1.ConditionTrue,
			Reason:  tunnelsv1.ReasonTunnelConnected,
			Message: fmt.Sprintf("Tunnel has %d active connections", len(cfTunnel.Connections)),
		})
	} else {
		meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
			Type:    tunnelsv1.TypeActive,
			Status:  metav1.ConditionFalse,
			Reason:  tunnelsv1.ReasonTunnelDisconnected,
			Message: "Tunnel exists but has no active connections",
		})
	}

	if err := r.Status().Update(ctx, tunnel); err != nil {
		return ctrl.Result{}, err
	}

	// Schedule next status check
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

// updateTunnelConfiguration updates tunnel ingress rules
func (r *CloudflareTunnelReconciler) updateTunnelConfiguration(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	if len(tunnel.Spec.Ingress) == 0 {
		return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
	}

	log.Info("Updating tunnel configuration", "tunnelID", tunnel.Status.TunnelID, "ingress_rules", len(tunnel.Spec.Ingress))

	// Convert ingress rules to Cloudflare format
	ingressRules := make([]cloudflare.UnvalidatedIngressRule, 0, len(tunnel.Spec.Ingress)+1)
	hasCatchAll := false

	for _, rule := range tunnel.Spec.Ingress {
		ingressRules = append(ingressRules, cloudflare.UnvalidatedIngressRule{
			Hostname: rule.Hostname,
			Service:  rule.Service,
		})
		// Check if this is already a catch-all rule (no hostname and http_status service)
		if rule.Hostname == "" && strings.HasPrefix(rule.Service, "http_status:") {
			hasCatchAll = true
		}
	}

	// Add catch-all rule only if one doesn't already exist
	if !hasCatchAll {
		ingressRules = append(ingressRules, cloudflare.UnvalidatedIngressRule{
			Service: "http_status:404",
		})
	}

	config := cloudflare.TunnelConfiguration{
		Ingress: ingressRules,
	}

	err := r.CFClient.UpdateTunnelConfiguration(ctx, tunnel.Spec.AccountID, tunnel.Status.TunnelID, config)
	if err != nil {
		log.Error(err, "Failed to update tunnel configuration")

		meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
			Type:    tunnelsv1.TypeDegraded,
			Status:  metav1.ConditionTrue,
			Reason:  tunnelsv1.ReasonAPIError,
			Message: fmt.Sprintf("Failed to update tunnel configuration: %v", err),
		})

		if err := r.Status().Update(ctx, tunnel); err != nil {
			log.Error(err, "Failed to update tunnel status")
		}
		return r.handleAPIError(err)
	}

	log.Info("Tunnel configuration updated successfully")
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

// handleAPIError handles Cloudflare API errors and determines retry behavior
func (r *CloudflareTunnelReconciler) handleAPIError(err error) (ctrl.Result, error) {
	var cfErr *cloudflare.Error
	if goerrors.As(err, &cfErr) {
		switch cfErr.StatusCode {
		case http.StatusTooManyRequests:
			return ctrl.Result{RequeueAfter: 2 * time.Minute}, nil
		case http.StatusNotFound:
			// Resource doesn't exist, treat as success for deletion
			return ctrl.Result{}, nil
		case http.StatusBadRequest:
			// Permanent error, don't retry
			return ctrl.Result{}, nil
		default:
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}
	}
	return ctrl.Result{RequeueAfter: 30 * time.Second}, err
}

// SetupWithManager sets up the controller with the Manager.
func (r *CloudflareTunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("cloudflare-tunnel-controller")

	return ctrl.NewControllerManagedBy(mgr).
		For(&tunnelsv1.CloudflareTunnel{}).
		Named("cloudflaretunnel").
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 3,
		}).
		Complete(r)
}
