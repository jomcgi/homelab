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
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/util/workqueue"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

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

	// Daemon mode configuration
	DaemonEnabled   bool
	DaemonAccountID string
	DaemonNamespace string
}

// +kubebuilder:rbac:groups=tunnels.tunnels.cloudflare.io,resources=cloudflaretunnels,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=tunnels.tunnels.cloudflare.io,resources=cloudflaretunnels/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=tunnels.tunnels.cloudflare.io,resources=cloudflaretunnels/finalizers,verbs=update
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
			// If daemon mode is enabled and this is the default tunnel, ensure it exists
			if r.DaemonEnabled && r.shouldManageTunnel(req) {
				log.Info("default daemon tunnel not found, creating it",
					"namespace", req.Namespace,
					"name", req.Name,
				)
				return r.ensureDefaultTunnel(ctx, req.NamespacedName)
			}
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

	// Delete daemon deployment first (if managed by operator)
	if err := r.deleteDaemonDeployment(ctx, tunnel); err != nil {
		log.Error(err, "Failed to delete daemon deployment")
		// Continue with cleanup even if deployment deletion fails
	}

	// Delete tunnel secret (if managed by operator)
	if err := r.deleteTunnelSecret(ctx, tunnel); err != nil {
		log.Error(err, "Failed to delete tunnel secret")
		// Continue with tunnel deletion even if secret deletion fails
	}

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

	// Update status with tunnel ID
	tunnel.Status.TunnelID = cfTunnel.ID
	tunnel.Status.Ready = true

	// Create tunnel secret and daemon deployment if daemon is enabled
	if tunnel.Spec.Daemon != nil && tunnel.Spec.Daemon.Enabled {
		// Get the tunnel token for daemon authentication
		tunnelToken, err := r.CFClient.GetTunnelToken(ctx, tunnel.Spec.AccountID, tunnel.Status.TunnelID)
		if err != nil {
			log.Error(err, "Failed to get tunnel token")
			meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
				Type:    tunnelsv1.TypeDegraded,
				Status:  metav1.ConditionTrue,
				Reason:  tunnelsv1.ReasonAPIError,
				Message: fmt.Sprintf("Failed to get tunnel token: %v", err),
			})
			if err := r.Status().Update(ctx, tunnel); err != nil {
				log.Error(err, "Failed to update tunnel status")
			}
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}

		// Log token metadata for debugging (never log the actual token)
		log.V(1).Info("retrieved tunnel token from Cloudflare",
			"tokenLength", len(tunnelToken),
			"isJWT", strings.HasPrefix(tunnelToken, "eyJ"))

		secretName, err := r.ensureTunnelSecret(ctx, tunnel, tunnelToken)
		if err != nil {
			log.Error(err, "Failed to create tunnel secret")
			meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
				Type:    tunnelsv1.TypeDegraded,
				Status:  metav1.ConditionTrue,
				Reason:  tunnelsv1.ReasonAPIError,
				Message: fmt.Sprintf("Failed to create tunnel secret: %v", err),
			})
			if err := r.Status().Update(ctx, tunnel); err != nil {
				log.Error(err, "Failed to update tunnel status")
			}
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}
		tunnel.Status.TunnelSecret = secretName

		// Create daemon deployment
		deploymentName, err := r.ensureDaemonDeployment(ctx, tunnel)
		if err != nil {
			log.Error(err, "Failed to create daemon deployment")
			meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
				Type:    tunnelsv1.TypeDegraded,
				Status:  metav1.ConditionTrue,
				Reason:  tunnelsv1.ReasonAPIError,
				Message: fmt.Sprintf("Failed to create daemon deployment: %v", err),
			})
			if err := r.Status().Update(ctx, tunnel); err != nil {
				log.Error(err, "Failed to update tunnel status")
			}
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}

		// Initialize daemon status
		if tunnel.Status.DaemonStatus == nil {
			tunnel.Status.DaemonStatus = &tunnelsv1.DaemonStatus{}
		}
		tunnel.Status.DaemonStatus.Enabled = true
		tunnel.Status.DaemonStatus.DeploymentName = deploymentName
		tunnel.Status.DaemonStatus.SecretName = secretName
	}

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

	// Update daemon status if daemon is enabled
	if tunnel.Spec.Daemon != nil && tunnel.Spec.Daemon.Enabled && tunnel.Status.DaemonStatus != nil {
		if err := r.updateDaemonStatus(ctx, tunnel); err != nil {
			log.Error(err, "Failed to update daemon status")
			// Continue with reconciliation even if daemon status update fails
		}
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

// ensureTunnelSecret creates or updates the tunnel secret with credentials
func (r *CloudflareTunnelReconciler) ensureTunnelSecret(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel, tunnelSecret string) (string, error) {
	log := logf.FromContext(ctx)

	// Use user-specified secret reference if provided
	if tunnel.Spec.Daemon != nil && tunnel.Spec.Daemon.SecretRef != nil {
		return tunnel.Spec.Daemon.SecretRef.Name, nil
	}

	// Generate secret name
	secretName := fmt.Sprintf("%s-tunnel-secret", tunnel.Name)

	// Create secret with the provided tunnel secret
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      secretName,
			Namespace: tunnel.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflare-tunnel",
				"app.kubernetes.io/instance":   tunnel.Name,
				"app.kubernetes.io/managed-by": "cloudflare-tunnel-operator",
			},
		},
		Type: corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			"tunnel-secret": []byte(tunnelSecret),
			"tunnel-id":     []byte(tunnel.Status.TunnelID),
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(tunnel, secret, r.Scheme); err != nil {
		return "", fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if secret already exists
	existing := &corev1.Secret{}
	err := r.Get(ctx, types.NamespacedName{Name: secretName, Namespace: tunnel.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new secret
			if err := r.Create(ctx, secret); err != nil {
				return "", fmt.Errorf("failed to create secret: %w", err)
			}
			log.V(1).Info("created tunnel secret", "secret", secretName)
		} else {
			return "", fmt.Errorf("failed to get secret: %w", err)
		}
	} else {
		// Update existing secret
		existing.Data = secret.Data
		existing.Labels = secret.Labels
		if err := r.Update(ctx, existing); err != nil {
			return "", fmt.Errorf("failed to update secret: %w", err)
		}
		log.V(1).Info("updated tunnel secret", "secret", secretName)
	}

	return secretName, nil
}

// ensureDaemonDeployment creates or updates the cloudflared daemon deployment
func (r *CloudflareTunnelReconciler) ensureDaemonDeployment(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) (string, error) {
	log := logf.FromContext(ctx)

	if tunnel.Spec.Daemon == nil || !tunnel.Spec.Daemon.Enabled {
		return "", fmt.Errorf("daemon not enabled")
	}

	deploymentName := fmt.Sprintf("%s-daemon", tunnel.Name)

	// Set default values
	image := tunnel.Spec.Daemon.Image
	if image == "" {
		image = "cloudflare/cloudflared:latest"
	}

	replicas := tunnel.Spec.Daemon.Replicas
	if replicas == nil {
		defaultReplicas := int32(2)
		replicas = &defaultReplicas
	}

	secretName := tunnel.Status.TunnelSecret
	secretKey := "tunnel-secret"
	if tunnel.Spec.Daemon.SecretRef != nil {
		secretName = tunnel.Spec.Daemon.SecretRef.Name
		if tunnel.Spec.Daemon.SecretRef.Key != "" {
			secretKey = tunnel.Spec.Daemon.SecretRef.Key
		}
	}

	// Create deployment
	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      deploymentName,
			Namespace: tunnel.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflared",
				"app.kubernetes.io/instance":   tunnel.Name,
				"app.kubernetes.io/managed-by": "cloudflare-tunnel-operator",
				"app.kubernetes.io/component":  "daemon",
			},
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app.kubernetes.io/name":     "cloudflared",
					"app.kubernetes.io/instance": tunnel.Name,
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app.kubernetes.io/name":     "cloudflared",
						"app.kubernetes.io/instance": tunnel.Name,
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  "cloudflared",
							Image: image,
							Args: []string{
								"tunnel",
								"--no-autoupdate",
								"--metrics",
								"127.0.0.1:2000",
								"run",
								"--token",
								"$(TUNNEL_TOKEN)",
							},
							Env: []corev1.EnvVar{
								{
									Name: "TUNNEL_TOKEN",
									ValueFrom: &corev1.EnvVarSource{
										SecretKeyRef: &corev1.SecretKeySelector{
											LocalObjectReference: corev1.LocalObjectReference{
												Name: secretName,
											},
											Key: secretKey,
										},
									},
								},
							},
							LivenessProbe: &corev1.Probe{
								ProbeHandler: corev1.ProbeHandler{
									Exec: &corev1.ExecAction{
										Command: []string{
											"cloudflared",
											"tunnel",
											"--metrics",
											"127.0.0.1:2000",
											"ready",
										},
									},
								},
								InitialDelaySeconds: 30,
								PeriodSeconds:       10,
								TimeoutSeconds:      5,
								FailureThreshold:    3,
							},
							ReadinessProbe: &corev1.Probe{
								ProbeHandler: corev1.ProbeHandler{
									Exec: &corev1.ExecAction{
										Command: []string{
											"cloudflared",
											"tunnel",
											"--metrics",
											"127.0.0.1:2000",
											"ready",
										},
									},
								},
								InitialDelaySeconds: 10,
								PeriodSeconds:       5,
								TimeoutSeconds:      5,
								FailureThreshold:    3,
							},
						},
					},
					RestartPolicy: corev1.RestartPolicyAlways,
				},
			},
		},
	}

	// Apply daemon configuration overrides
	if tunnel.Spec.Daemon.Resources.Limits != nil || tunnel.Spec.Daemon.Resources.Requests != nil {
		deployment.Spec.Template.Spec.Containers[0].Resources = tunnel.Spec.Daemon.Resources
	}

	if tunnel.Spec.Daemon.NodeSelector != nil {
		deployment.Spec.Template.Spec.NodeSelector = tunnel.Spec.Daemon.NodeSelector
	}

	if tunnel.Spec.Daemon.Tolerations != nil {
		deployment.Spec.Template.Spec.Tolerations = tunnel.Spec.Daemon.Tolerations
	}

	if tunnel.Spec.Daemon.Affinity != nil {
		deployment.Spec.Template.Spec.Affinity = tunnel.Spec.Daemon.Affinity
	}

	if tunnel.Spec.Daemon.ServiceAccount != "" {
		deployment.Spec.Template.Spec.ServiceAccountName = tunnel.Spec.Daemon.ServiceAccount
	}

	if tunnel.Spec.Daemon.Annotations != nil {
		if deployment.Spec.Template.Annotations == nil {
			deployment.Spec.Template.Annotations = make(map[string]string)
		}
		for k, v := range tunnel.Spec.Daemon.Annotations {
			deployment.Spec.Template.Annotations[k] = v
		}
	}

	if tunnel.Spec.Daemon.Labels != nil {
		for k, v := range tunnel.Spec.Daemon.Labels {
			deployment.Spec.Template.Labels[k] = v
			deployment.Labels[k] = v
		}
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(tunnel, deployment, r.Scheme); err != nil {
		return "", fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if deployment already exists
	existing := &appsv1.Deployment{}
	err := r.Get(ctx, types.NamespacedName{Name: deploymentName, Namespace: tunnel.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new deployment
			if err := r.Create(ctx, deployment); err != nil {
				return "", fmt.Errorf("failed to create deployment: %w", err)
			}
			log.V(1).Info("created daemon deployment", "deployment", deploymentName)
		} else {
			return "", fmt.Errorf("failed to get deployment: %w", err)
		}
	} else {
		// Update existing deployment
		existing.Spec = deployment.Spec
		existing.Labels = deployment.Labels
		if err := r.Update(ctx, existing); err != nil {
			return "", fmt.Errorf("failed to update deployment: %w", err)
		}
		log.V(1).Info("updated daemon deployment", "deployment", deploymentName)
	}

	return deploymentName, nil
}

// updateDaemonStatus updates the daemon status based on deployment state
func (r *CloudflareTunnelReconciler) updateDaemonStatus(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) error {
	if tunnel.Status.DaemonStatus == nil || tunnel.Status.DaemonStatus.DeploymentName == "" {
		return nil
	}

	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, types.NamespacedName{
		Name:      tunnel.Status.DaemonStatus.DeploymentName,
		Namespace: tunnel.Namespace,
	}, deployment)

	if err != nil {
		if errors.IsNotFound(err) {
			// Deployment not found, reset daemon status
			tunnel.Status.DaemonStatus.Replicas = 0
			tunnel.Status.DaemonStatus.ReadyReplicas = 0
			return nil
		}
		return fmt.Errorf("failed to get daemon deployment: %w", err)
	}

	// Update daemon status from deployment
	tunnel.Status.DaemonStatus.Replicas = deployment.Status.Replicas
	tunnel.Status.DaemonStatus.ReadyReplicas = deployment.Status.ReadyReplicas

	return nil
}

// deleteDaemonDeployment removes the daemon deployment
func (r *CloudflareTunnelReconciler) deleteDaemonDeployment(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) error {
	if tunnel.Status.DaemonStatus == nil || tunnel.Status.DaemonStatus.DeploymentName == "" {
		return nil
	}

	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      tunnel.Status.DaemonStatus.DeploymentName,
			Namespace: tunnel.Namespace,
		},
	}

	err := r.Delete(ctx, deployment)
	if err != nil && !errors.IsNotFound(err) {
		return fmt.Errorf("failed to delete daemon deployment: %w", err)
	}

	return nil
}

// deleteTunnelSecret removes the tunnel secret
func (r *CloudflareTunnelReconciler) deleteTunnelSecret(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) error {
	if tunnel.Status.TunnelSecret == "" {
		return nil
	}

	// Skip deletion if using user-specified secret
	if tunnel.Spec.Daemon != nil && tunnel.Spec.Daemon.SecretRef != nil {
		return nil
	}

	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      tunnel.Status.TunnelSecret,
			Namespace: tunnel.Namespace,
		},
	}

	err := r.Delete(ctx, secret)
	if err != nil && !errors.IsNotFound(err) {
		return fmt.Errorf("failed to delete tunnel secret: %w", err)
	}

	return nil
}

// shouldManageTunnel checks if this reconciliation request is for the default daemon tunnel
func (r *CloudflareTunnelReconciler) shouldManageTunnel(req ctrl.Request) bool {
	return req.Namespace == r.DaemonNamespace && req.Name == "default-daemon-tunnel"
}

// ensureDefaultTunnel creates the default daemon tunnel if it doesn't exist
func (r *CloudflareTunnelReconciler) ensureDefaultTunnel(ctx context.Context, namespacedName types.NamespacedName) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	log.Info("creating default daemon tunnel",
		"crdName", namespacedName.Name,
		"namespace", namespacedName.Namespace,
	)

	// Create default tunnel - note that the tunnel name in Cloudflare will be generated
	// uniquely based on the CRD's UID after creation, so we use a placeholder here
	defaultTunnel := &tunnelsv1.CloudflareTunnel{
		ObjectMeta: metav1.ObjectMeta{
			Name:      namespacedName.Name,
			Namespace: namespacedName.Namespace,
		},
		Spec: tunnelsv1.CloudflareTunnelSpec{
			// Name will be auto-generated as {crdName}-{uid-prefix} by the reconciler
			Name:      "", // Empty name signals auto-generation
			AccountID: r.DaemonAccountID,
			Daemon: &tunnelsv1.DaemonConfig{
				Enabled:  true,
				Replicas: func() *int32 { r := int32(1); return &r }(),
				Image:    "cloudflare/cloudflared:latest",
			},
			Ingress: []tunnelsv1.TunnelIngress{
				{
					Service: "http_status:404", // Default catch-all only
				},
			},
		},
	}

	if err := r.Create(ctx, defaultTunnel); err != nil {
		if errors.IsAlreadyExists(err) {
			log.V(1).Info("default tunnel already exists (race condition)")
			// Requeue to reconcile the newly created tunnel
			return ctrl.Result{Requeue: true}, nil
		}
		log.Error(err, "failed to create default tunnel")
		// Retry after backoff
		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	log.Info("default daemon tunnel CRD created successfully, will auto-generate unique tunnel name during reconciliation",
		"crdName", namespacedName.Name,
	)

	// Requeue immediately to reconcile the newly created tunnel
	return ctrl.Result{Requeue: true}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *CloudflareTunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("cloudflare-tunnel-controller")

	builder := ctrl.NewControllerManagedBy(mgr).
		For(&tunnelsv1.CloudflareTunnel{}).
		Named("cloudflaretunnel")

	// If daemon mode is enabled, add periodic reconciliation for the default tunnel
	if r.DaemonEnabled {
		// Enqueue the default tunnel for reconciliation every 30 seconds
		builder = builder.WatchesRawSource(
			&periodicEnqueueSource{
				period: 30 * time.Second,
				object: types.NamespacedName{
					Name:      "default-daemon-tunnel",
					Namespace: r.DaemonNamespace,
				},
			},
		)
	}

	return builder.Complete(r)
}

// periodicEnqueueSource is a source that periodically enqueues a specific object for reconciliation
type periodicEnqueueSource struct {
	period time.Duration
	object types.NamespacedName
}

func (s *periodicEnqueueSource) Start(ctx context.Context, queue workqueue.TypedRateLimitingInterface[reconcile.Request]) error {
	go func() {
		ticker := time.NewTicker(s.period)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				// Enqueue the object for reconciliation
				queue.Add(reconcile.Request{NamespacedName: s.object})
			}
		}
	}()
	return nil
}
