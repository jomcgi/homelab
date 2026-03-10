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

	appsv1 "k8s.io/api/apps/v1"
	autoscalingv2 "k8s.io/api/autoscaling/v2"
	corev1 "k8s.io/api/core/v1"
	policyv1 "k8s.io/api/policy/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/utils/ptr"
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
	// GatewayFinalizerName is the finalizer used by the Gateway controller
	GatewayFinalizerName = "gateway.cloudflare.io/finalizer"

	// GatewayAnnotationTunnelID stores the Cloudflare tunnel ID
	GatewayAnnotationTunnelID = "gateway.cloudflare.io/tunnel-id"

	// GatewayAnnotationAccountID stores the Cloudflare account ID
	GatewayAnnotationAccountID = "gateway.cloudflare.io/account-id"

	// DefaultCloudflaredImage is the default cloudflared image with a pinned version
	// Using a specific version ensures reliability and prevents Docker Hub rate limiting issues
	DefaultCloudflaredImage = "cloudflare/cloudflared:2025.11.1"

	// DefaultCloudflaredReplicas is the default number of cloudflared replicas
	DefaultCloudflaredReplicas = 2
)

// GatewayReconciler reconciles a Gateway object
type GatewayReconciler struct {
	client.Client
	Scheme           *runtime.Scheme
	tracer           trace.Tracer
	CloudflaredImage string // Configurable cloudflared image
}

// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gateways/finalizers,verbs=update
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gatewayclasses,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=autoscaling,resources=horizontalpodautoscalers,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=policy,resources=poddisruptionbudgets,verbs=get;list;watch;create;update;patch;delete

// Reconcile is part of the main kubernetes reconciliation loop
func (r *GatewayReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// Start span for reconciliation
	ctx, span := r.tracer.Start(ctx, "Gateway.Reconcile",
		trace.WithAttributes(
			attribute.String("k8s.resource.name", req.Name),
			attribute.String("k8s.resource.namespace", req.Namespace),
		),
	)
	defer span.End()

	log := log.FromContext(ctx)

	// Fetch the Gateway instance
	var gateway gatewayv1.Gateway
	if err := r.Get(ctx, req.NamespacedName, &gateway); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("Gateway resource not found, ignoring since object must be deleted")
			span.SetStatus(codes.Ok, "resource not found")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get Gateway")
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get resource")
		return ctrl.Result{}, err
	}

	// Only reconcile Gateways with our GatewayClass
	if gateway.Spec.GatewayClassName != "cloudflare" {
		log.V(1).Info("Gateway not managed by cloudflare GatewayClass",
			"gatewayClassName", gateway.Spec.GatewayClassName,
		)
		span.SetStatus(codes.Ok, "not managed by cloudflare GatewayClass")
		return ctrl.Result{}, nil
	}

	// Get tunnel ID from annotations (if exists)
	tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]
	accountID := gateway.Annotations[GatewayAnnotationAccountID]

	span.SetAttributes(
		attribute.String("gateway.name", gateway.Name),
		attribute.String("gateway.namespace", gateway.Namespace),
		attribute.String("gateway.class", string(gateway.Spec.GatewayClassName)),
		attribute.String("tunnel.id", tunnelID),
		attribute.String("account.id", accountID),
	)

	// Handle deletion
	if gateway.DeletionTimestamp != nil {
		result, err := r.handleDeletion(ctx, &gateway)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "deletion failed")
		} else {
			span.SetStatus(codes.Ok, "resource deleted")
		}
		return result, err
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(&gateway, GatewayFinalizerName) {
		controllerutil.AddFinalizer(&gateway, GatewayFinalizerName)
		span.AddEvent("finalizer added")
		return ctrl.Result{}, r.Update(ctx, &gateway)
	}

	// Handle creation/update
	result, err := r.handleCreateOrUpdate(ctx, &gateway)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "reconciliation failed")
	} else {
		span.SetStatus(codes.Ok, "reconciliation successful")
	}
	return result, err
}

// handleDeletion handles the deletion of a Gateway
func (r *GatewayReconciler) handleDeletion(ctx context.Context, gateway *gatewayv1.Gateway) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	if !controllerutil.ContainsFinalizer(gateway, GatewayFinalizerName) {
		return ctrl.Result{}, nil
	}

	log.Info("Deleting Gateway", "gateway", gateway.Name, "namespace", gateway.Namespace)

	// Note: CloudflareTunnel CRD will be automatically deleted via OwnerReference
	// This triggers CloudflareTunnel controller's finalizer which deletes the tunnel from Cloudflare
	// Deployment, HPA, and PDB are also automatically deleted via OwnerReference

	// Just remove our finalizer - Kubernetes garbage collection handles the rest
	controllerutil.RemoveFinalizer(gateway, GatewayFinalizerName)
	return ctrl.Result{}, r.Update(ctx, gateway)
}

// handleCreateOrUpdate handles the creation or update of a Gateway
func (r *GatewayReconciler) handleCreateOrUpdate(ctx context.Context, gateway *gatewayv1.Gateway) (ctrl.Result, error) {
	// Get tunnel ID from annotations
	tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]

	// Create tunnel if it doesn't exist
	if tunnelID == "" {
		return r.createTunnel(ctx, gateway)
	}

	// Update tunnel status
	return r.updateTunnelStatus(ctx, gateway)
}

// createTunnel creates a new CloudflareTunnel CRD for the Gateway
func (r *GatewayReconciler) createTunnel(ctx context.Context, gateway *gatewayv1.Gateway) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Get account ID from GatewayClass credentials
	accountID, err := r.getAccountID(ctx, gateway)
	if err != nil {
		log.Error(err, "Failed to get account ID")

		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               string(gatewayv1.GatewayConditionAccepted),
			Status:             metav1.ConditionFalse,
			Reason:             "InvalidCredentials",
			Message:            fmt.Sprintf("Failed to get account ID: %v", err),
			ObservedGeneration: gateway.Generation,
		})

		if err := r.Status().Update(ctx, gateway); err != nil {
			log.Error(err, "Failed to update Gateway status")
		}

		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	// Generate namespace-scoped tunnel name for traffic isolation
	tunnelName := fmt.Sprintf("%s-gateway-tunnel", gateway.Name)
	log.Info("Creating CloudflareTunnel CRD", "tunnelName", tunnelName, "accountID", accountID)

	// Set Programmed condition to Unknown (creating)
	meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
		Type:               string(gatewayv1.GatewayConditionProgrammed),
		Status:             metav1.ConditionUnknown,
		Reason:             "Creating",
		Message:            "Creating CloudflareTunnel CRD",
		ObservedGeneration: gateway.Generation,
	})
	if err := r.Status().Update(ctx, gateway); err != nil {
		return ctrl.Result{}, err
	}

	// Create CloudflareTunnel CRD with OwnerReference for automatic cleanup
	tunnel, err := r.ensureCloudflaredTunnelCRD(ctx, gateway, tunnelName, accountID)
	if err != nil {
		log.Error(err, "Failed to create CloudflareTunnel CRD")
		return r.handleAPIError(ctx, gateway, err, "Failed to create CloudflareTunnel CRD")
	}

	// Wait for tunnel to be ready (has TunnelID and SecretName)
	if !tunnel.Status.Ready || tunnel.Status.TunnelID == "" || tunnel.Status.SecretName == "" {
		log.Info("Waiting for CloudflareTunnel to be ready",
			"tunnel", tunnel.Name,
			"ready", tunnel.Status.Ready,
			"tunnelID", tunnel.Status.TunnelID,
			"secretName", tunnel.Status.SecretName,
		)

		// Only update status if condition has actually changed to avoid conflicts
		existingCondition := meta.FindStatusCondition(gateway.Status.Conditions, string(gatewayv1.GatewayConditionProgrammed))
		if existingCondition == nil || existingCondition.Reason != "WaitingForTunnel" {
			meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
				Type:               string(gatewayv1.GatewayConditionProgrammed),
				Status:             metav1.ConditionUnknown,
				Reason:             "WaitingForTunnel",
				Message:            "Waiting for CloudflareTunnel to be ready",
				ObservedGeneration: gateway.Generation,
			})

			if err := r.Status().Update(ctx, gateway); err != nil {
				// Conflict errors are expected with multiple replicas; requeue without error
				if errors.IsConflict(err) {
					log.V(1).Info("Conflict updating gateway status, will retry")
					return ctrl.Result{Requeue: true}, nil
				}
				return ctrl.Result{}, err
			}
		}

		// Requeue to check tunnel status
		return ctrl.Result{RequeueAfter: 5 * time.Second}, nil
	}

	// Tunnel is ready - create cloudflared deployment using the tunnel's secret
	deploymentName, err := r.ensureCloudflaredDeployment(ctx, gateway, tunnel.Status.SecretName)
	if err != nil {
		log.Error(err, "Failed to create cloudflared deployment")
		return r.handleAPIError(ctx, gateway, err, "Failed to create cloudflared deployment")
	}

	log.Info("Gateway tunnel infrastructure created successfully",
		"tunnelCRD", tunnel.Name,
		"tunnelID", tunnel.Status.TunnelID,
		"secret", tunnel.Status.SecretName,
		"deployment", deploymentName,
	)

	// Store tunnel ID in annotations for status updates
	if gateway.Annotations == nil {
		gateway.Annotations = make(map[string]string)
	}
	gateway.Annotations[GatewayAnnotationTunnelID] = tunnel.Status.TunnelID
	gateway.Annotations[GatewayAnnotationAccountID] = accountID

	if err := r.Update(ctx, gateway); err != nil {
		log.Error(err, "Failed to update Gateway annotations")
		return ctrl.Result{}, err
	}

	// CRITICAL: Refetch Gateway to get latest resourceVersion after annotation update
	// Without this, the status update will conflict with the updated resourceVersion
	if err := r.Get(ctx, client.ObjectKeyFromObject(gateway), gateway); err != nil {
		log.Error(err, "Failed to refetch Gateway after annotation update")
		return ctrl.Result{}, err
	}

	// Set Gateway status conditions
	meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
		Type:               string(gatewayv1.GatewayConditionAccepted),
		Status:             metav1.ConditionTrue,
		Reason:             "Accepted",
		Message:            "Gateway configuration is valid",
		ObservedGeneration: gateway.Generation,
	})

	meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
		Type:               string(gatewayv1.GatewayConditionProgrammed),
		Status:             metav1.ConditionTrue,
		Reason:             "Programmed",
		Message:            fmt.Sprintf("Tunnel %s created successfully", tunnel.Status.TunnelID),
		ObservedGeneration: gateway.Generation,
	})

	// Set Gateway address (tunnel CNAME target)
	gateway.Status.Addresses = []gatewayv1.GatewayStatusAddress{
		{
			Type:  ptr.To(gatewayv1.HostnameAddressType),
			Value: fmt.Sprintf("%s.cfargotunnel.com", tunnel.Status.TunnelID),
		},
	}

	if err := r.Status().Update(ctx, gateway); err != nil {
		return ctrl.Result{}, err
	}

	// No requeue needed - controller-runtime will reconcile on actual changes
	log.Info("Gateway successfully reconciled", "tunnelID", tunnel.Status.TunnelID)
	return ctrl.Result{}, nil
}

// ensureCloudflaredTunnelCRD creates or gets the CloudflareTunnel CRD for the Gateway
func (r *GatewayReconciler) ensureCloudflaredTunnelCRD(ctx context.Context, gateway *gatewayv1.Gateway, tunnelName, accountID string) (*tunnelsv1.CloudflareTunnel, error) {
	log := log.FromContext(ctx)

	// Check if tunnel CRD already exists
	tunnel := &tunnelsv1.CloudflareTunnel{}
	err := r.Get(ctx, types.NamespacedName{Name: tunnelName, Namespace: gateway.Namespace}, tunnel)
	if err == nil {
		// Tunnel already exists
		log.Info("CloudflareTunnel CRD already exists", "tunnel", tunnelName)
		return tunnel, nil
	}

	if !errors.IsNotFound(err) {
		return nil, fmt.Errorf("failed to get CloudflareTunnel: %w", err)
	}

	// Create new CloudflareTunnel CRD with OwnerReference
	tunnel = &tunnelsv1.CloudflareTunnel{
		ObjectMeta: metav1.ObjectMeta{
			Name:      tunnelName,
			Namespace: gateway.Namespace,
			OwnerReferences: []metav1.OwnerReference{
				{
					APIVersion:         gatewayv1.GroupVersion.String(),
					Kind:               "Gateway",
					Name:               gateway.Name,
					UID:                gateway.UID,
					Controller:         ptr.To(true),
					BlockOwnerDeletion: ptr.To(true),
				},
			},
		},
		Spec: tunnelsv1.CloudflareTunnelSpec{
			Name:      tunnelName,
			AccountID: accountID,
		},
	}

	if err := r.Create(ctx, tunnel); err != nil {
		return nil, fmt.Errorf("failed to create CloudflareTunnel CRD: %w", err)
	}

	log.Info("Created CloudflareTunnel CRD", "tunnel", tunnelName, "accountID", accountID)
	return tunnel, nil
}

// updateTunnelStatus updates the Gateway status from CloudflareTunnel CRD
func (r *GatewayReconciler) updateTunnelStatus(ctx context.Context, gateway *gatewayv1.Gateway) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]
	if tunnelID == "" {
		log.Error(fmt.Errorf("missing tunnel ID"), "Tunnel ID not found in annotations")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
	}

	// Get CloudflareTunnel CRD to check status
	tunnelName := fmt.Sprintf("%s-gateway-tunnel", gateway.Name)
	tunnel := &tunnelsv1.CloudflareTunnel{}
	err := r.Get(ctx, types.NamespacedName{Name: tunnelName, Namespace: gateway.Namespace}, tunnel)
	if err != nil {
		if errors.IsNotFound(err) {
			log.Info("CloudflareTunnel CRD not found, recreating", "tunnel", tunnelName)

			// Clear tunnel ID to trigger recreation
			delete(gateway.Annotations, GatewayAnnotationTunnelID)
			delete(gateway.Annotations, GatewayAnnotationAccountID)
			if err := r.Update(ctx, gateway); err != nil {
				return ctrl.Result{}, err
			}

			return ctrl.Result{Requeue: true}, nil
		}

		log.Error(err, "Failed to get CloudflareTunnel CRD")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	// Update Gateway status based on tunnel status
	if tunnel.Status.Active {
		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               string(gatewayv1.GatewayConditionProgrammed),
			Status:             metav1.ConditionTrue,
			Reason:             "Programmed",
			Message:            "Tunnel is active with connections",
			ObservedGeneration: gateway.Generation,
		})
	} else if tunnel.Status.Ready {
		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               string(gatewayv1.GatewayConditionProgrammed),
			Status:             metav1.ConditionTrue,
			Reason:             "Programmed",
			Message:            "Tunnel exists but has no active connections",
			ObservedGeneration: gateway.Generation,
		})
	} else {
		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               string(gatewayv1.GatewayConditionProgrammed),
			Status:             metav1.ConditionUnknown,
			Reason:             "Pending",
			Message:            "Waiting for tunnel to be ready",
			ObservedGeneration: gateway.Generation,
		})
	}

	if err := r.Status().Update(ctx, gateway); err != nil {
		return ctrl.Result{}, err
	}

	// No requeue needed - controller will reconcile when CloudflareTunnel status changes
	// via watch on CloudflareTunnel resources (owner reference)
	log.V(1).Info("Gateway status updated from tunnel", "active", tunnel.Status.Active, "ready", tunnel.Status.Ready)
	return ctrl.Result{}, nil
}

// getCloudflareClient creates a Cloudflare API client using credentials from the GatewayClass
func (r *GatewayReconciler) getCloudflareClient(ctx context.Context, gateway *gatewayv1.Gateway) (*cfclient.TunnelClient, error) {
	// Get GatewayClass
	var gatewayClass gatewayv1.GatewayClass
	if err := r.Get(ctx, types.NamespacedName{Name: string(gateway.Spec.GatewayClassName)}, &gatewayClass); err != nil {
		return nil, fmt.Errorf("failed to get GatewayClass: %w", err)
	}

	// Get credentials from parametersRef
	if gatewayClass.Spec.ParametersRef == nil {
		return nil, fmt.Errorf("GatewayClass has no parametersRef")
	}

	ref := gatewayClass.Spec.ParametersRef
	if ref.Kind != "Secret" {
		return nil, fmt.Errorf("unsupported parametersRef kind: %s", ref.Kind)
	}

	if ref.Namespace == nil {
		return nil, fmt.Errorf("parametersRef namespace is required")
	}

	// Get the credentials Secret
	var secret corev1.Secret
	if err := r.Get(ctx, types.NamespacedName{
		Name:      ref.Name,
		Namespace: string(*ref.Namespace),
	}, &secret); err != nil {
		return nil, fmt.Errorf("failed to get credentials secret: %w", err)
	}

	// Extract API token
	apiToken, ok := secret.Data["CLOUDFLARE_API_TOKEN"]
	if !ok {
		return nil, fmt.Errorf("credentials secret missing CLOUDFLARE_API_TOKEN")
	}

	// Create Cloudflare client
	return cfclient.NewTunnelClient(string(apiToken))
}

// getAccountID retrieves the Cloudflare account ID from the GatewayClass credentials
func (r *GatewayReconciler) getAccountID(ctx context.Context, gateway *gatewayv1.Gateway) (string, error) {
	// Get GatewayClass
	var gatewayClass gatewayv1.GatewayClass
	if err := r.Get(ctx, types.NamespacedName{Name: string(gateway.Spec.GatewayClassName)}, &gatewayClass); err != nil {
		return "", fmt.Errorf("failed to get GatewayClass: %w", err)
	}

	// Get credentials from parametersRef
	if gatewayClass.Spec.ParametersRef == nil {
		return "", fmt.Errorf("GatewayClass has no parametersRef")
	}

	ref := gatewayClass.Spec.ParametersRef
	if ref.Namespace == nil {
		return "", fmt.Errorf("parametersRef namespace is required")
	}

	// Get the credentials Secret
	var secret corev1.Secret
	if err := r.Get(ctx, types.NamespacedName{
		Name:      ref.Name,
		Namespace: string(*ref.Namespace),
	}, &secret); err != nil {
		return "", fmt.Errorf("failed to get credentials secret: %w", err)
	}

	// Extract account ID
	accountID, ok := secret.Data["CLOUDFLARE_ACCOUNT_ID"]
	if !ok {
		return "", fmt.Errorf("credentials secret missing CLOUDFLARE_ACCOUNT_ID")
	}

	return string(accountID), nil
}

// ensureTunnelSecret creates or updates the tunnel secret with credentials
func (r *GatewayReconciler) ensureTunnelSecret(ctx context.Context, gateway *gatewayv1.Gateway, tunnelID, tunnelToken string) (string, error) {
	log := log.FromContext(ctx)

	secretName := fmt.Sprintf("cloudflare-tunnel-%s", gateway.Name)

	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      secretName,
			Namespace: gateway.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflare-tunnel",
				"app.kubernetes.io/instance":   gateway.Name,
				"app.kubernetes.io/managed-by": "cloudflare-gateway-operator",
			},
		},
		Type: corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			"tunnel-token": []byte(tunnelToken),
			"tunnel-id":    []byte(tunnelID),
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(gateway, secret, r.Scheme); err != nil {
		return "", fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if secret already exists
	existing := &corev1.Secret{}
	err := r.Get(ctx, types.NamespacedName{Name: secretName, Namespace: gateway.Namespace}, existing)
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

// getCloudflaredImage returns the cloudflared image to use, either from configuration or default
func (r *GatewayReconciler) getCloudflaredImage() string {
	if r.CloudflaredImage != "" {
		return r.CloudflaredImage
	}
	return DefaultCloudflaredImage
}

// ensureCloudflaredDeployment creates or updates the cloudflared daemon deployment
func (r *GatewayReconciler) ensureCloudflaredDeployment(ctx context.Context, gateway *gatewayv1.Gateway, secretName string) (string, error) {
	log := log.FromContext(ctx)

	deploymentName := fmt.Sprintf("cloudflared-%s", gateway.Name)
	replicas := int32(DefaultCloudflaredReplicas)

	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      deploymentName,
			Namespace: gateway.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflared",
				"app.kubernetes.io/instance":   gateway.Name,
				"app.kubernetes.io/managed-by": "cloudflare-gateway-operator",
				"app.kubernetes.io/component":  "daemon",
			},
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app.kubernetes.io/name":     "cloudflared",
					"app.kubernetes.io/instance": gateway.Name,
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app.kubernetes.io/name":     "cloudflared",
						"app.kubernetes.io/instance": gateway.Name,
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  "cloudflared",
							Image: r.getCloudflaredImage(),
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
											Key: "tunnel-token",
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
							// Resource limits for safe scaling and noisy neighbor protection
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("100m"),
									corev1.ResourceMemory: resource.MustParse("128Mi"),
								},
								Limits: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("1000m"),
									corev1.ResourceMemory: resource.MustParse("512Mi"),
								},
							},
						},
					},
					RestartPolicy: corev1.RestartPolicyAlways,
				},
			},
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(gateway, deployment, r.Scheme); err != nil {
		return "", fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if deployment already exists
	existing := &appsv1.Deployment{}
	err := r.Get(ctx, types.NamespacedName{Name: deploymentName, Namespace: gateway.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new deployment
			if err := r.Create(ctx, deployment); err != nil {
				return "", fmt.Errorf("failed to create deployment: %w", err)
			}
			log.V(1).Info("created cloudflared deployment", "deployment", deploymentName)
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
		log.V(1).Info("updated cloudflared deployment", "deployment", deploymentName)
	}

	// Ensure HPA for auto-scaling
	if err := r.ensureHPA(ctx, gateway, deployment); err != nil {
		log.Error(err, "Failed to ensure HPA", "deployment", deploymentName)
		// Continue even if HPA creation fails
	}

	// Ensure PodDisruptionBudget for high availability
	if err := r.ensurePDB(ctx, gateway, deployment); err != nil {
		log.Error(err, "Failed to ensure PDB", "deployment", deploymentName)
		// Continue even if PDB creation fails
	}

	return deploymentName, nil
}

// deleteCloudflaredDeployment removes the cloudflared deployment
func (r *GatewayReconciler) deleteCloudflaredDeployment(ctx context.Context, gateway *gatewayv1.Gateway) error {
	deploymentName := fmt.Sprintf("cloudflared-%s", gateway.Name)

	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      deploymentName,
			Namespace: gateway.Namespace,
		},
	}

	err := r.Delete(ctx, deployment)
	if err != nil && !errors.IsNotFound(err) {
		return fmt.Errorf("failed to delete cloudflared deployment: %w", err)
	}

	return nil
}

// deleteTunnelSecret removes the tunnel secret
func (r *GatewayReconciler) deleteTunnelSecret(ctx context.Context, gateway *gatewayv1.Gateway) error {
	secretName := fmt.Sprintf("cloudflare-tunnel-%s", gateway.Name)

	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      secretName,
			Namespace: gateway.Namespace,
		},
	}

	err := r.Delete(ctx, secret)
	if err != nil && !errors.IsNotFound(err) {
		return fmt.Errorf("failed to delete tunnel secret: %w", err)
	}

	return nil
}

// ensureHPA creates or updates HorizontalPodAutoscaler for cloudflared deployment
func (r *GatewayReconciler) ensureHPA(ctx context.Context, gateway *gatewayv1.Gateway, deployment *appsv1.Deployment) error {
	log := log.FromContext(ctx)

	hpaName := fmt.Sprintf("%s-hpa", deployment.Name)

	hpa := &autoscalingv2.HorizontalPodAutoscaler{
		ObjectMeta: metav1.ObjectMeta{
			Name:      hpaName,
			Namespace: gateway.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflared-hpa",
				"app.kubernetes.io/instance":   gateway.Name,
				"app.kubernetes.io/managed-by": "cloudflare-gateway-operator",
			},
		},
		Spec: autoscalingv2.HorizontalPodAutoscalerSpec{
			ScaleTargetRef: autoscalingv2.CrossVersionObjectReference{
				APIVersion: "apps/v1",
				Kind:       "Deployment",
				Name:       deployment.Name,
			},
			MinReplicas: ptr.To(int32(2)), // High availability
			MaxReplicas: 10,               // Cost control
			Metrics: []autoscalingv2.MetricSpec{
				{
					Type: autoscalingv2.ResourceMetricSourceType,
					Resource: &autoscalingv2.ResourceMetricSource{
						Name: corev1.ResourceCPU,
						Target: autoscalingv2.MetricTarget{
							Type:               autoscalingv2.UtilizationMetricType,
							AverageUtilization: ptr.To(int32(70)),
						},
					},
				},
				{
					Type: autoscalingv2.ResourceMetricSourceType,
					Resource: &autoscalingv2.ResourceMetricSource{
						Name: corev1.ResourceMemory,
						Target: autoscalingv2.MetricTarget{
							Type:               autoscalingv2.UtilizationMetricType,
							AverageUtilization: ptr.To(int32(80)),
						},
					},
				},
			},
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(gateway, hpa, r.Scheme); err != nil {
		return fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if HPA already exists
	existing := &autoscalingv2.HorizontalPodAutoscaler{}
	err := r.Get(ctx, types.NamespacedName{Name: hpaName, Namespace: gateway.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new HPA
			if err := r.Create(ctx, hpa); err != nil {
				return fmt.Errorf("failed to create HPA: %w", err)
			}
			log.V(1).Info("created HPA", "hpa", hpaName)
		} else {
			return fmt.Errorf("failed to get HPA: %w", err)
		}
	} else {
		// Update existing HPA
		existing.Spec = hpa.Spec
		existing.Labels = hpa.Labels
		if err := r.Update(ctx, existing); err != nil {
			return fmt.Errorf("failed to update HPA: %w", err)
		}
		log.V(1).Info("updated HPA", "hpa", hpaName)
	}

	return nil
}

// ensurePDB creates or updates PodDisruptionBudget for cloudflared deployment
func (r *GatewayReconciler) ensurePDB(ctx context.Context, gateway *gatewayv1.Gateway, deployment *appsv1.Deployment) error {
	log := log.FromContext(ctx)

	pdbName := fmt.Sprintf("%s-pdb", deployment.Name)

	pdb := &policyv1.PodDisruptionBudget{
		ObjectMeta: metav1.ObjectMeta{
			Name:      pdbName,
			Namespace: gateway.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "cloudflared-pdb",
				"app.kubernetes.io/instance":   gateway.Name,
				"app.kubernetes.io/managed-by": "cloudflare-gateway-operator",
			},
		},
		Spec: policyv1.PodDisruptionBudgetSpec{
			MinAvailable: ptr.To(intstr.FromInt(1)),
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app.kubernetes.io/name":     "cloudflared",
					"app.kubernetes.io/instance": gateway.Name,
				},
			},
		},
	}

	// Set owner reference
	if err := controllerutil.SetControllerReference(gateway, pdb, r.Scheme); err != nil {
		return fmt.Errorf("failed to set controller reference: %w", err)
	}

	// Check if PDB already exists
	existing := &policyv1.PodDisruptionBudget{}
	err := r.Get(ctx, types.NamespacedName{Name: pdbName, Namespace: gateway.Namespace}, existing)
	if err != nil {
		if errors.IsNotFound(err) {
			// Create new PDB
			if err := r.Create(ctx, pdb); err != nil {
				return fmt.Errorf("failed to create PDB: %w", err)
			}
			log.V(1).Info("created PDB", "pdb", pdbName)
		} else {
			return fmt.Errorf("failed to get PDB: %w", err)
		}
	} else {
		// Update existing PDB spec (cannot update minAvailable directly, need to recreate)
		// PDB spec is immutable, so we skip update
		log.V(1).Info("PDB already exists", "pdb", pdbName)
	}

	return nil
}

// handleAPIError handles Cloudflare API errors and updates Gateway status
func (r *GatewayReconciler) handleAPIError(ctx context.Context, gateway *gatewayv1.Gateway, err error, message string) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	log.Error(err, message)

	meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
		Type:               string(gatewayv1.GatewayConditionProgrammed),
		Status:             metav1.ConditionFalse,
		Reason:             "CloudflareAPIError",
		Message:            fmt.Sprintf("%s: %v", message, err),
		ObservedGeneration: gateway.Generation,
	})

	if err := r.Status().Update(ctx, gateway); err != nil {
		log.Error(err, "Failed to update Gateway status")
	}

	return ctrl.Result{RequeueAfter: 30 * time.Second}, err
}

// SetupWithManager sets up the controller with the Manager.
func (r *GatewayReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("gateway-controller")

	return ctrl.NewControllerManagedBy(mgr).
		For(&gatewayv1.Gateway{}).
		Owns(&tunnelsv1.CloudflareTunnel{}).
		Owns(&appsv1.Deployment{}).
		Owns(&autoscalingv2.HorizontalPodAutoscaler{}).
		Owns(&policyv1.PodDisruptionBudget{}).
		Named("gateway").
		WithOptions(controller.Options{
			// Use 1 to prevent concurrent reconciliations of the same Gateway
			// from racing to update status and causing conflict errors
			MaxConcurrentReconciles: 1,
		}).
		Complete(r)
}
