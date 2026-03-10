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
	"strings"
	"time"

	"github.com/cloudflare/cloudflare-go"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	cfclient "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/cloudflare"
	sm "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/statemachine"
)

const (
	// FinalizerName is the finalizer used by this controller
	FinalizerName = "tunnels.cloudflare.io/finalizer"
)

// CloudflareTunnelReconciler reconciles a CloudflareTunnel object
type CloudflareTunnelReconciler struct {
	client.Client
	Scheme     *runtime.Scheme
	CFClient   cfclient.TunnelClientInterface
	Calculator *sm.CloudflareTunnelCalculator
	Observer   sm.TransitionObserver
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
	log := logf.FromContext(ctx)
	startTime := time.Now()

	// 1. Fetch the resource
	var tunnel tunnelsv1.CloudflareTunnel
	if err := r.Get(ctx, req.NamespacedName, &tunnel); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("CloudflareTunnel resource not found, ignoring since object must be deleted")
			sm.CleanupResourceMetrics(req.Namespace, req.Name)
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// 2. Calculate current state from status
	currentState := r.Calculator.Calculate(&tunnel)
	phase := currentState.Phase()
	log.V(1).Info("Calculated state", "phase", phase)

	// 3. Visit the state to determine next action
	visitor := &tunnelVisitor{
		reconciler: r,
		ctx:        ctx,
	}
	result := sm.Visit(currentState, visitor)

	// 4. Record metrics
	sm.RecordReconcile(phase, time.Since(startTime), result.Error == nil)

	return result.Result, result.Error
}

// VisitResult is returned by visitor methods
type VisitResult struct {
	Result ctrl.Result
	Error  error
}

// tunnelVisitor implements sm.CloudflareTunnelVisitor[VisitResult]
type tunnelVisitor struct {
	reconciler *CloudflareTunnelReconciler
	ctx        context.Context
}

// Compile-time check that tunnelVisitor implements the visitor interface
var _ sm.CloudflareTunnelVisitor[VisitResult] = (*tunnelVisitor)(nil)

// VisitPending handles the Pending state - add finalizer and start creation
func (v *tunnelVisitor) VisitPending(s sm.CloudflareTunnelPending) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Handle deletion
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(tunnel, FinalizerName) {
		log.Info("Adding finalizer")
		controllerutil.AddFinalizer(tunnel, FinalizerName)
		if err := v.reconciler.Update(v.ctx, tunnel); err != nil {
			return VisitResult{Error: err}
		}
		return VisitResult{Result: ctrl.Result{Requeue: true}}
	}

	// Transition to CreatingTunnel
	log.Info("Starting tunnel creation")
	newState := s.StartCreation()
	return v.updateStatus(newState)
}

// VisitCreatingTunnel handles the CreatingTunnel state - create tunnel in Cloudflare
func (v *tunnelVisitor) VisitCreatingTunnel(s sm.CloudflareTunnelCreatingTunnel) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Handle deletion
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	// Generate tunnel name
	tunnelName := tunnel.Spec.Name
	if tunnelName == "" {
		tunnelName = fmt.Sprintf("%s-%s", tunnel.Name, string(tunnel.UID)[:8])
		log.Info("Auto-generating unique tunnel name", "tunnelName", tunnelName)
	}

	log.Info("Creating CloudflareTunnel", "tunnelName", tunnelName, "accountID", tunnel.Spec.AccountID)

	// Create tunnel in Cloudflare
	cfTunnel, _, err := v.reconciler.CFClient.CreateTunnel(v.ctx, tunnel.Spec.AccountID, tunnelName)
	if err != nil {
		// Check if tunnel already exists (adopt it)
		if strings.Contains(err.Error(), "(1013)") || strings.Contains(err.Error(), "already have a tunnel with this name") {
			log.Info("Tunnel name already exists, attempting to adopt existing tunnel", "tunnelName", tunnelName)
			return v.adoptExistingTunnel(s, tunnelName, tunnel.Spec.AccountID)
		}

		// Handle error
		return v.handleError(s, err)
	}

	// Transition to CreatingSecret with tunnelID
	log.Info("Tunnel created successfully", "tunnelID", cfTunnel.ID)
	newState := s.TunnelCreated(cfTunnel.ID)
	return v.updateStatus(newState)
}

// VisitCreatingSecret handles the CreatingSecret state - create K8s secret with tunnel token
func (v *tunnelVisitor) VisitCreatingSecret(s sm.CloudflareTunnelCreatingSecret) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Handle deletion
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	log.Info("Creating tunnel secret", "tunnelID", s.TunnelID)

	// Get tunnel token from Cloudflare
	tunnelToken, err := v.reconciler.CFClient.GetTunnelToken(v.ctx, tunnel.Spec.AccountID, s.TunnelID)
	if err != nil {
		log.Error(err, "Failed to get tunnel token")
		return v.handleError(s, err)
	}

	// Create the secret
	secretName := fmt.Sprintf("%s-tunnel-token", tunnel.Name)
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      secretName,
			Namespace: tunnel.Namespace,
			OwnerReferences: []metav1.OwnerReference{
				{
					APIVersion:         tunnel.APIVersion,
					Kind:               tunnel.Kind,
					Name:               tunnel.Name,
					UID:                tunnel.UID,
					Controller:         ptr.To(true),
					BlockOwnerDeletion: ptr.To(true),
				},
			},
		},
		StringData: map[string]string{
			"tunnel-token": tunnelToken,
		},
		Type: corev1.SecretTypeOpaque,
	}

	// Create or update the secret
	existingSecret := &corev1.Secret{}
	err = v.reconciler.Get(v.ctx, types.NamespacedName{Name: secretName, Namespace: tunnel.Namespace}, existingSecret)
	if err != nil {
		if errors.IsNotFound(err) {
			if err := v.reconciler.Create(v.ctx, secret); err != nil {
				log.Error(err, "Failed to create secret")
				return v.handleError(s, err)
			}
			log.Info("Created tunnel secret", "secretName", secretName)
		} else {
			log.Error(err, "Failed to get secret")
			return v.handleError(s, err)
		}
	} else {
		existingSecret.StringData = secret.StringData
		if err := v.reconciler.Update(v.ctx, existingSecret); err != nil {
			log.Error(err, "Failed to update secret")
			return v.handleError(s, err)
		}
		log.Info("Updated tunnel secret", "secretName", secretName)
	}

	// Transition to ConfiguringIngress
	newState := s.SecretCreated(secretName)
	return v.updateStatus(newState)
}

// VisitConfiguringIngress handles the ConfiguringIngress state - configure tunnel ingress rules
func (v *tunnelVisitor) VisitConfiguringIngress(s sm.CloudflareTunnelConfiguringIngress) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Handle deletion
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	// Configure ingress rules if specified
	if len(tunnel.Spec.Ingress) > 0 {
		log.Info("Configuring tunnel ingress", "tunnelID", s.TunnelID, "rules", len(tunnel.Spec.Ingress))

		// Convert ingress rules to Cloudflare format
		ingressRules := make([]cloudflare.UnvalidatedIngressRule, 0, len(tunnel.Spec.Ingress)+1)
		hasCatchAll := false

		for _, rule := range tunnel.Spec.Ingress {
			ingressRules = append(ingressRules, cloudflare.UnvalidatedIngressRule{
				Hostname: rule.Hostname,
				Service:  rule.Service,
			})
			if rule.Hostname == "" && strings.HasPrefix(rule.Service, "http_status:") {
				hasCatchAll = true
			}
		}

		// Add catch-all rule if needed
		if !hasCatchAll {
			ingressRules = append(ingressRules, cloudflare.UnvalidatedIngressRule{
				Service: "http_status:404",
			})
		}

		config := cloudflare.TunnelConfiguration{
			Ingress: ingressRules,
		}

		err := v.reconciler.CFClient.UpdateTunnelConfiguration(v.ctx, tunnel.Spec.AccountID, s.TunnelID, config)
		if err != nil {
			log.Error(err, "Failed to update tunnel configuration")
			return v.handleError(s, err)
		}

		log.Info("Tunnel configuration updated successfully")
	}

	// Transition to Ready
	newState := s.IngressConfigured(false) // Will check active status on next reconcile
	return v.updateStatus(newState)
}

// VisitReady handles the Ready state - monitor tunnel and handle spec changes
func (v *tunnelVisitor) VisitReady(s sm.CloudflareTunnelReady) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Handle deletion
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	// Check for spec changes
	if sm.HasSpecChanged(tunnel) {
		log.Info("Spec changed, reconfiguring ingress")
		// Update status to ConfiguringIngress while preserving tunnelID and secretName
		tunnel.Status.Phase = sm.PhaseConfiguringIngress
		tunnel.Status.ObservedGeneration = tunnel.Generation
		if err := v.reconciler.Status().Update(v.ctx, tunnel); err != nil {
			return VisitResult{Error: err}
		}
		return VisitResult{Result: ctrl.Result{Requeue: true}}
	}

	// Periodic status check - verify tunnel exists and get connection status
	cfTunnel, err := v.reconciler.CFClient.GetTunnel(v.ctx, tunnel.Spec.AccountID, s.TunnelID)
	if err != nil {
		if cfclient.IsNotFoundError(err) {
			log.Info("Tunnel deleted externally, will recreate")
			// Reset to Pending to recreate
			tunnel.Status.Phase = sm.PhasePending
			tunnel.Status.TunnelID = ""
			tunnel.Status.SecretName = ""
			if err := v.reconciler.Status().Update(v.ctx, tunnel); err != nil {
				return VisitResult{Error: err}
			}
			return VisitResult{Result: ctrl.Result{Requeue: true}}
		}
		log.Error(err, "Failed to get tunnel status")
		// Don't fail, just requeue
		return VisitResult{Result: ctrl.Result{RequeueAfter: s.RequeueAfter()}}
	}

	// Update active status based on tunnel connections
	hasConnections := len(cfTunnel.Connections) > 0
	if hasConnections != s.Active {
		log.Info("Updating active status", "active", hasConnections, "connections", len(cfTunnel.Connections))
		tunnel.Status.Active = hasConnections
		if err := v.reconciler.Status().Update(v.ctx, tunnel); err != nil {
			return VisitResult{Error: err}
		}
	}

	// All good, requeue for next check
	log.V(1).Info("Tunnel ready", "active", s.Active)
	return VisitResult{Result: ctrl.Result{RequeueAfter: s.RequeueAfter()}}
}

// VisitFailed handles the Failed state - retry or give up
func (v *tunnelVisitor) VisitFailed(s sm.CloudflareTunnelFailed) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Handle deletion (always allow deletion from Failed)
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	log.Info("In Failed state", "lastState", s.LastState, "retryCount", s.RetryCount, "error", s.ErrorMessage)

	// Check if we can retry
	if newState := s.Retry(); newState != nil {
		log.Info("Retrying from Failed state", "retryCount", s.RetryCount)
		return v.updateStatus(*newState)
	}

	// Max retries exceeded - stay in Failed, requeue slowly
	log.Info("Max retries exceeded, staying in Failed state")
	return VisitResult{Result: ctrl.Result{RequeueAfter: s.RetryBackoff()}}
}

// VisitDeletingTunnel handles the DeletingTunnel state - cleanup Cloudflare resources
func (v *tunnelVisitor) VisitDeletingTunnel(s sm.CloudflareTunnelDeletingTunnel) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	log.Info("Deleting tunnel from Cloudflare", "tunnelID", s.TunnelID)

	// Delete tunnel from Cloudflare if it exists
	if s.TunnelID != "" {
		err := v.reconciler.CFClient.DeleteTunnel(v.ctx, tunnel.Spec.AccountID, s.TunnelID)
		if err != nil && !cfclient.IsNotFoundError(err) {
			log.Error(err, "Failed to delete tunnel from Cloudflare")
			return VisitResult{Result: ctrl.Result{RequeueAfter: 30 * time.Second}}
		}
		log.Info("Tunnel deleted from Cloudflare")
	}

	// Secret will be garbage collected via OwnerReferences

	// Transition to Deleted
	newState := s.DeletionComplete()
	return v.updateStatus(newState)
}

// VisitDeleted handles the Deleted state - remove finalizer
func (v *tunnelVisitor) VisitDeleted(s sm.CloudflareTunnelDeleted) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	// Remove finalizer
	if controllerutil.ContainsFinalizer(tunnel, FinalizerName) {
		log.Info("Removing finalizer")
		controllerutil.RemoveFinalizer(tunnel, FinalizerName)
		if err := v.reconciler.Update(v.ctx, tunnel); err != nil {
			return VisitResult{Error: err}
		}
	}

	// Cleanup metrics
	sm.CleanupResourceMetrics(tunnel.Namespace, tunnel.Name)

	log.Info("CloudflareTunnel deletion complete")
	return VisitResult{}
}

// VisitUnknown handles the Unknown state - reset to Pending
func (v *tunnelVisitor) VisitUnknown(s sm.CloudflareTunnelUnknown) VisitResult {
	tunnel := s.Resource()
	log := logf.FromContext(v.ctx)

	log.Info("Unknown state detected, resetting to Pending", "observedPhase", s.ObservedPhase)

	// Handle deletion
	if !tunnel.DeletionTimestamp.IsZero() {
		return v.transitionToDeleting(s)
	}

	// Reset to Pending
	newState := s.Reset()
	return v.updateStatus(newState)
}

// Helper methods

// updateStatus updates the resource status with the new state using Server-Side Apply
func (v *tunnelVisitor) updateStatus(newState sm.CloudflareTunnelState) VisitResult {
	// Create SSA patch from the state
	patch, err := sm.SSAPatch(newState)
	if err != nil {
		return VisitResult{Error: fmt.Errorf("failed to create SSA patch: %w", err)}
	}

	// Apply the patch to update status
	resource := newState.Resource()
	if err := v.reconciler.Status().Patch(v.ctx, resource, patch, client.FieldOwner(sm.FieldManager)); err != nil {
		return VisitResult{Error: err}
	}

	return VisitResult{Result: ctrl.Result{RequeueAfter: newState.RequeueAfter()}}
}

// handleError transitions to Failed state for permanent errors or requeues for transient errors
func (v *tunnelVisitor) handleError(from sm.CloudflareTunnelState, err error) VisitResult {
	log := logf.FromContext(v.ctx)

	// Classify error
	if cfclient.IsRetryableError(err) {
		log.Info("Transient error, will retry", "error", err)
		sm.RecordError("transient")
		return VisitResult{Result: ctrl.Result{RequeueAfter: 30 * time.Second}}
	}

	// Permanent error - transition to Failed
	log.Error(err, "Permanent error, transitioning to Failed")
	sm.RecordError("permanent")

	// Get current retry count
	retryCount := 0
	if failed, ok := from.(sm.CloudflareTunnelFailed); ok {
		retryCount = failed.RetryCount + 1
	}

	// Create Failed state manually since MarkFailed is only available from specific states
	tunnel := from.Resource()
	tunnel.Status.Phase = sm.PhaseFailed
	tunnel.Status.LastState = from.Phase()
	tunnel.Status.ErrorMessage = err.Error()
	tunnel.Status.RetryCount = retryCount
	tunnel.Status.ObservedGeneration = tunnel.Generation

	if updateErr := v.reconciler.Status().Update(v.ctx, tunnel); updateErr != nil {
		return VisitResult{Error: updateErr}
	}

	return VisitResult{Result: ctrl.Result{RequeueAfter: 1 * time.Minute}}
}

// transitionToDeleting handles the deletion trigger from any state
func (v *tunnelVisitor) transitionToDeleting(from sm.CloudflareTunnelState) VisitResult {
	tunnel := from.Resource()
	log := logf.FromContext(v.ctx)

	log.Info("Resource marked for deletion, transitioning to DeletingTunnel")

	// Get tunnelID from current state or status
	tunnelID := tunnel.Status.TunnelID

	// Create DeletingTunnel state
	tunnel.Status.Phase = sm.PhaseDeletingTunnel
	tunnel.Status.TunnelID = tunnelID // Preserve for deletion

	if err := v.reconciler.Status().Update(v.ctx, tunnel); err != nil {
		return VisitResult{Error: err}
	}

	return VisitResult{Result: ctrl.Result{Requeue: true}}
}

// adoptExistingTunnel attempts to adopt an existing tunnel with the same name
func (v *tunnelVisitor) adoptExistingTunnel(s sm.CloudflareTunnelCreatingTunnel, tunnelName, accountID string) VisitResult {
	log := logf.FromContext(v.ctx)

	// List all tunnels to find the one with this name
	tunnels, err := v.reconciler.CFClient.ListTunnels(v.ctx, accountID)
	if err != nil {
		log.Error(err, "Failed to list tunnels for adoption")
		return v.handleError(s, err)
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
		err := fmt.Errorf("tunnel name exists but not found in list: %s", tunnelName)
		log.Error(err, "Failed to find existing tunnel")
		return v.handleError(s, err)
	}

	log.Info("Successfully adopted existing tunnel", "tunnelName", tunnelName, "tunnelID", existingTunnel.ID)

	// Transition to CreatingSecret with adopted tunnelID
	newState := s.TunnelCreated(existingTunnel.ID)
	return v.updateStatus(newState)
}

// SetupWithManager sets up the controller with the Manager.
func (r *CloudflareTunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&tunnelsv1.CloudflareTunnel{}).
		Named("cloudflaretunnel").
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 3,
		}).
		Complete(r)
}
