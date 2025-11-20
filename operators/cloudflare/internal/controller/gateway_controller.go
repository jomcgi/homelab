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

	cfclient "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
	"github.com/jomcgi/homelab/operators/cloudflare/internal/telemetry"
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

	// DefaultCloudflaredImage is the default cloudflared image
	DefaultCloudflaredImage = "cloudflare/cloudflared:latest"

	// DefaultCloudflaredReplicas is the default number of cloudflared replicas
	DefaultCloudflaredReplicas = 2
)

// GatewayReconciler reconciles a Gateway object
type GatewayReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	tracer trace.Tracer
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

	// Get tunnel ID and account ID from annotations
	tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]
	accountID := gateway.Annotations[GatewayAnnotationAccountID]

	// Delete cloudflared deployment
	if err := r.deleteCloudflaredDeployment(ctx, gateway); err != nil {
		log.Error(err, "Failed to delete cloudflared deployment")
		// Continue with cleanup even if deployment deletion fails
	}

	// Delete tunnel secret
	if err := r.deleteTunnelSecret(ctx, gateway); err != nil {
		log.Error(err, "Failed to delete tunnel secret")
		// Continue with tunnel deletion even if secret deletion fails
	}

	// Delete tunnel from Cloudflare if it exists
	if tunnelID != "" && accountID != "" {
		// Get Cloudflare client
		cfClient, err := r.getCloudflareClient(ctx, gateway)
		if err != nil {
			log.Error(err, "Failed to get Cloudflare client, skipping tunnel deletion")
		} else {
			err := cfClient.DeleteTunnel(ctx, accountID, tunnelID)
			if err != nil && !cfclient.IsNotFoundError(err) {
				log.Error(err, "Failed to delete tunnel from Cloudflare")

				// Update status to indicate deletion failure
				meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
					Type:               string(gatewayv1.GatewayConditionAccepted),
					Status:             metav1.ConditionFalse,
					Reason:             "DeletionFailed",
					Message:            fmt.Sprintf("Failed to delete tunnel: %v", err),
					ObservedGeneration: gateway.Generation,
				})
				if err := r.Status().Update(ctx, gateway); err != nil {
					log.Error(err, "Failed to update Gateway status")
				}

				// Retry deletion after backoff
				return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
			}
		}
	}

	// Remove finalizer
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

// createTunnel creates a new Cloudflare tunnel for the Gateway
func (r *GatewayReconciler) createTunnel(ctx context.Context, gateway *gatewayv1.Gateway) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Get Cloudflare client
	cfClient, err := r.getCloudflareClient(ctx, gateway)
	if err != nil {
		log.Error(err, "Failed to get Cloudflare client")

		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               string(gatewayv1.GatewayConditionAccepted),
			Status:             metav1.ConditionFalse,
			Reason:             "InvalidCredentials",
			Message:            fmt.Sprintf("Failed to get Cloudflare client: %v", err),
			ObservedGeneration: gateway.Generation,
		})

		if err := r.Status().Update(ctx, gateway); err != nil {
			log.Error(err, "Failed to update Gateway status")
		}

		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

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
	tunnelName := fmt.Sprintf("namespace-%s-tunnel", gateway.Namespace)
	log.Info("Creating namespace-scoped Cloudflare tunnel", "tunnelName", tunnelName, "accountID", accountID)

	// Set Programmed condition to Unknown (creating)
	meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
		Type:               string(gatewayv1.GatewayConditionProgrammed),
		Status:             metav1.ConditionUnknown,
		Reason:             "Creating",
		Message:            "Creating Cloudflare tunnel",
		ObservedGeneration: gateway.Generation,
	})
	if err := r.Status().Update(ctx, gateway); err != nil {
		return ctrl.Result{}, err
	}

	// Create tunnel via Cloudflare API
	cfTunnel, _, err := cfClient.CreateTunnel(ctx, accountID, tunnelName)
	if err != nil {
		// Check if tunnel already exists
		if strings.Contains(err.Error(), "(1013)") || strings.Contains(err.Error(), "already have a tunnel with this name") {
			log.Info("Tunnel name already exists, attempting to adopt existing tunnel", "tunnelName", tunnelName)

			// List all tunnels to find the one with this name
			tunnels, listErr := cfClient.ListTunnels(ctx, accountID)
			if listErr != nil {
				log.Error(listErr, "Failed to list tunnels for adoption")
				return r.handleAPIError(ctx, gateway, listErr, "Failed to adopt tunnel")
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
				return r.handleAPIError(ctx, gateway, fmt.Errorf("tunnel name exists but not found"), "Tunnel adoption failed")
			}

			log.Info("Successfully adopted existing tunnel", "tunnelName", tunnelName, "tunnelID", existingTunnel.ID)
			cfTunnel = existingTunnel
		} else {
			log.Error(err, "Failed to create tunnel")
			return r.handleAPIError(ctx, gateway, err, "Failed to create tunnel")
		}
	}

	// Store tunnel ID and account ID in annotations
	if gateway.Annotations == nil {
		gateway.Annotations = make(map[string]string)
	}
	gateway.Annotations[GatewayAnnotationTunnelID] = cfTunnel.ID
	gateway.Annotations[GatewayAnnotationAccountID] = accountID

	if err := r.Update(ctx, gateway); err != nil {
		log.Error(err, "Failed to update Gateway annotations")
		return ctrl.Result{}, err
	}

	// Get tunnel token for cloudflared
	tunnelToken, err := cfClient.GetTunnelToken(ctx, accountID, cfTunnel.ID)
	if err != nil {
		log.Error(err, "Failed to get tunnel token")
		return r.handleAPIError(ctx, gateway, err, "Failed to get tunnel token")
	}

	// Create tunnel secret
	secretName, err := r.ensureTunnelSecret(ctx, gateway, cfTunnel.ID, tunnelToken)
	if err != nil {
		log.Error(err, "Failed to create tunnel secret")
		return r.handleAPIError(ctx, gateway, err, "Failed to create tunnel secret")
	}

	// Create cloudflared deployment
	deploymentName, err := r.ensureCloudflaredDeployment(ctx, gateway, secretName)
	if err != nil {
		log.Error(err, "Failed to create cloudflared deployment")
		return r.handleAPIError(ctx, gateway, err, "Failed to create cloudflared deployment")
	}

	log.Info("Cloudflare tunnel created successfully",
		"tunnelID", cfTunnel.ID,
		"secret", secretName,
		"deployment", deploymentName,
	)

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
		Message:            fmt.Sprintf("Tunnel %s created successfully", cfTunnel.ID),
		ObservedGeneration: gateway.Generation,
	})

	// Set Gateway address (tunnel CNAME target)
	gateway.Status.Addresses = []gatewayv1.GatewayStatusAddress{
		{
			Type:  ptr.To(gatewayv1.HostnameAddressType),
			Value: fmt.Sprintf("%s.cfargotunnel.com", cfTunnel.ID),
		},
	}

	if err := r.Status().Update(ctx, gateway); err != nil {
		return ctrl.Result{}, err
	}

	// Schedule status check
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

// updateTunnelStatus updates the Gateway status from Cloudflare
func (r *GatewayReconciler) updateTunnelStatus(ctx context.Context, gateway *gatewayv1.Gateway) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]
	accountID := gateway.Annotations[GatewayAnnotationAccountID]

	if tunnelID == "" || accountID == "" {
		log.Error(fmt.Errorf("missing tunnel metadata"), "Tunnel ID or Account ID not found in annotations")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
	}

	// Get Cloudflare client
	cfClient, err := r.getCloudflareClient(ctx, gateway)
	if err != nil {
		log.Error(err, "Failed to get Cloudflare client")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	// Get tunnel status from Cloudflare
	cfTunnel, err := cfClient.GetTunnel(ctx, accountID, tunnelID)
	if err != nil {
		if cfclient.IsNotFoundError(err) {
			log.Info("Tunnel not found in Cloudflare, recreating", "tunnelID", tunnelID)

			// Clear tunnel ID to trigger recreation
			delete(gateway.Annotations, GatewayAnnotationTunnelID)
			delete(gateway.Annotations, GatewayAnnotationAccountID)
			if err := r.Update(ctx, gateway); err != nil {
				return ctrl.Result{}, err
			}

			return r.createTunnel(ctx, gateway)
		}

		log.Error(err, "Failed to get tunnel status")
		return r.handleAPIError(ctx, gateway, err, "Failed to get tunnel status")
	}

	// Update Ready status based on tunnel connections
	hasConnections := len(cfTunnel.Connections) > 0

	if hasConnections {
		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               "Ready",
			Status:             metav1.ConditionTrue,
			Reason:             "Connected",
			Message:            fmt.Sprintf("Tunnel has %d active connections", len(cfTunnel.Connections)),
			ObservedGeneration: gateway.Generation,
		})
	} else {
		meta.SetStatusCondition(&gateway.Status.Conditions, metav1.Condition{
			Type:               "Ready",
			Status:             metav1.ConditionFalse,
			Reason:             "Disconnected",
			Message:            "Tunnel exists but has no active connections",
			ObservedGeneration: gateway.Generation,
		})
	}

	if err := r.Status().Update(ctx, gateway); err != nil {
		return ctrl.Result{}, err
	}

	// Schedule next status check
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
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
							Image: DefaultCloudflaredImage,
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
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Secret{}).
		Owns(&autoscalingv2.HorizontalPodAutoscaler{}).
		Owns(&policyv1.PodDisruptionBudget{}).
		Named("gateway").
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 3,
		}).
		Complete(r)
}
