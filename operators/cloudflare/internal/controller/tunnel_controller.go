package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cfapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
)

const (
	FinalizerTunnelCleanup = "cloudflare.io/tunnel-cleanup"
)

type TunnelReconciler struct {
	client.Client
	Scheme           *runtime.Scheme
	CloudflareClient *cfapi.Client
	TunnelID         string // Current tunnel ID managed by this operator instance
	Namespace        string // Namespace where operator resources are deployed
	OperatorPodName  string // Name of the operator pod for ownership
}

func (r *TunnelReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Allow empty requests (used by TunnelInitializer for setup)
	if req.Name == "" && req.Namespace == "" {
		log.Info("Processing empty request (tunnel initialization)")
	} else {
		// This controller only processes the tunnel secret, ignore all other secrets
		if req.Name != "cloudflare-operator-tunnel" || req.Namespace != r.Namespace {
			log.Info("Ignoring secret - not tunnel secret", "secretName", req.Name, "secretNamespace", req.Namespace, "operatorNamespace", r.Namespace)
			return ctrl.Result{}, nil
		}
		log.Info("Processing tunnel secret", "secretName", req.Name, "secretNamespace", req.Namespace)
	}

	// This controller manages a single shared tunnel for the operator instance
	// The tunnel is created when the operator starts and deleted when it's removed
	
	// Check if we already have a tunnel secret
	tunnelSecret := &corev1.Secret{}
	secretName := "cloudflare-operator-tunnel"
	err := r.Get(ctx, client.ObjectKey{Name: secretName, Namespace: r.Namespace}, tunnelSecret)
	
	if err != nil {
		if client.IgnoreNotFound(err) != nil {
			log.Error(err, "Failed to get tunnel secret")
			return ctrl.Result{RequeueAfter: time.Minute * 2}, nil
		}
		
		// Secret doesn't exist, create a new tunnel
		// operatorNamespace already defined above
		
		// Generate a unique tunnel name based on namespace and timestamp
		tunnelName := fmt.Sprintf("k8s-operator-%s-%d", r.Namespace, time.Now().Unix())
		
		log.Info("Creating operator-managed Cloudflare tunnel", "name", tunnelName)
		
		tunnel, err := r.CloudflareClient.CreateTunnel(ctx, tunnelName)
		if err != nil {
			log.Error(err, "Failed to create tunnel")
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}

		tunnelID := tunnel.ID
		log.Info("✅ Created Cloudflare tunnel", "tunnelId", tunnelID, "name", tunnelName)

		// Get tunnel credentials for deployment
		credentials, err := r.CloudflareClient.GetTunnelCredentials(ctx, tunnelID)
		if err != nil {
			log.Error(err, "Failed to get tunnel credentials", "tunnelId", tunnelID)
			// Clean up the tunnel since we can't use it without credentials
			if deleteErr := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); deleteErr != nil {
				log.Error(deleteErr, "Failed to delete tunnel after credentials error", "tunnelId", tunnelID)
			}
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}

		// Store the tunnel info in a secret
		if err := r.createTunnelSecret(ctx, r.Namespace, tunnelName, tunnelID, credentials); err != nil {
			log.Error(err, "Failed to create tunnel secret")
			// Clean up the tunnel since we can't store its credentials
			if deleteErr := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); deleteErr != nil {
				log.Error(deleteErr, "Failed to delete tunnel after secret error", "tunnelId", tunnelID)
			}
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}

		log.Info("✅ Operator tunnel setup complete", "tunnelId", tunnelID)
		
		// Cleanup will be handled by SIGTERM handler when operator terminates
		
		// Create shared cloudflared deployment after tunnel is set up
		if err := r.ensureSharedCloudflaredDeployment(ctx); err != nil {
			log.Error(err, "Failed to ensure shared cloudflared deployment")
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}
		
		// Store tunnel ID in memory for cleanup on shutdown
		r.TunnelID = tunnelID
		return ctrl.Result{RequeueAfter: time.Minute * 10}, nil
	}

	// Handle secret deletion with finalizer
	if !tunnelSecret.DeletionTimestamp.IsZero() {
		return r.handleTunnelDeletion(ctx, tunnelSecret)
	}

	// Tunnel secret exists, validate it before reusing
	if tunnelIDBytes, ok := tunnelSecret.Data["tunnel-id"]; ok {
		tunnelID := string(tunnelIDBytes)
		
		// Validate that the tunnel still exists in Cloudflare API
		if err := r.CloudflareClient.ValidateExistingTunnel(ctx, tunnelID); err != nil {
			log.Info("Existing tunnel is invalid, will recreate", "tunnelId", tunnelID, "error", err.Error())
			
			// Delete the stale secret and recreate tunnel (use replacement strategy for invalid tunnels)
			if err := r.Delete(ctx, tunnelSecret); err != nil {
				log.Error(err, "Failed to delete stale tunnel secret")
				return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
			}
			
			// Requeue to trigger tunnel creation
			return ctrl.Result{Requeue: true}, nil
		}
		
		// Validate credentials format if available
		if credentialsBytes, hasCredentials := tunnelSecret.Data["credentials"]; hasCredentials {
			var credentials map[string]string
			if err := json.Unmarshal(credentialsBytes, &credentials); err != nil {
				log.Info("Tunnel credentials are corrupted, will recreate", "tunnelId", tunnelID, "error", err.Error())
				
				// Delete the stale secret and recreate tunnel
				if err := r.Delete(ctx, tunnelSecret); err != nil {
					log.Error(err, "Failed to delete corrupted tunnel secret")
					return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
				}
				
				// Requeue to trigger tunnel creation
				return ctrl.Result{Requeue: true}, nil
			}
			
			// Validate credentials format
			if err := r.CloudflareClient.ValidateTunnelCredentials(credentials); err != nil {
				log.Info("Tunnel credentials are invalid, will refresh", "tunnelId", tunnelID, "error", err.Error())
				
				// Tunnel exists but credentials are bad - fetch fresh credentials and patch secret
				freshCredentials, err := r.CloudflareClient.GetTunnelCredentials(ctx, tunnelID)
				if err != nil {
					log.Error(err, "Failed to get fresh tunnel credentials", "tunnelId", tunnelID)
					// If we can't get fresh credentials, delete and recreate
					if err := r.Delete(ctx, tunnelSecret); err != nil {
						log.Error(err, "Failed to delete invalid tunnel secret")
						return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
					}
					return ctrl.Result{Requeue: true}, nil
				}
				
				// Patch the existing secret with fresh credentials
				tunnelName := string(tunnelSecret.Data["tunnel-name"])
				if tunnelName == "" {
					tunnelName = fmt.Sprintf("k8s-operator-refreshed-%d", time.Now().Unix())
				}
				
				if err := r.patchTunnelSecret(ctx, tunnelSecret, tunnelName, tunnelID, freshCredentials); err != nil {
					log.Error(err, "Failed to patch tunnel secret with fresh credentials")
					return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
				}
				
				log.Info("✅ Refreshed tunnel credentials", "tunnelId", tunnelID)
			}
		}
		
		r.TunnelID = tunnelID
		log.V(1).Info("Operator tunnel validated and configured", "tunnelId", r.TunnelID)
	}
	
	// Even if tunnel exists, ensure cloudflared deployment is running
	if err := r.ensureSharedCloudflaredDeployment(ctx); err != nil {
		log.Error(err, "Failed to ensure shared cloudflared deployment")
		return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
	}
	
	// Always validate ConfigMap to prevent drift
	if err := r.ensureCloudflaredConfig(ctx); err != nil {
		log.Error(err, "Failed to validate cloudflared configuration")
		return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
	}

	return ctrl.Result{RequeueAfter: time.Minute * 10}, nil
}

// createTunnelSecret creates a Kubernetes secret containing the tunnel credentials
func (r *TunnelReconciler) createTunnelSecret(ctx context.Context, namespace, tunnelName, tunnelID string, credentials map[string]string) error {
	log := log.FromContext(ctx)
	
	// Get the operator pod to set as owner
	operatorPod := &corev1.Pod{}
	if err := r.Get(ctx, client.ObjectKey{Name: r.OperatorPodName, Namespace: namespace}, operatorPod); err != nil {
		log.Error(err, "Failed to get operator pod for ownership", "podName", r.OperatorPodName)
		return fmt.Errorf("failed to get operator pod for ownership: %w", err)
	}
	
	secretName := "cloudflare-operator-tunnel"
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      secretName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":                          "cloudflare-operator",
				"cloudflare.io/tunnel-name":    tunnelName,
				"cloudflare.io/tunnel-id":      tunnelID,
				"cloudflare.io/managed-by":     "cloudflare-operator",
			},
			Finalizers: []string{FinalizerTunnelCleanup},
			OwnerReferences: []metav1.OwnerReference{
				{
					APIVersion: "v1",
					Kind:       "Pod",
					Name:       operatorPod.Name,
					UID:        operatorPod.UID,
					Controller: func() *bool { b := true; return &b }(),
				},
			},
		},
		Type: corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			"token":       []byte(credentials["TunnelSecret"]), // For backward compatibility
			"tunnel-id":   []byte(tunnelID),
			"tunnel-name": []byte(tunnelName),
			"credentials": r.createCredentialsJSON(credentials),
		},
	}

	if err := r.Create(ctx, secret); err != nil {
		return fmt.Errorf("failed to create tunnel secret: %w", err)
	}

	log.Info("✅ Created tunnel secret with operator pod ownership", "secretName", secretName, "tunnelId", tunnelID, "ownerPod", operatorPod.Name)
	return nil
}

// patchTunnelSecret updates an existing tunnel secret with new credentials
func (r *TunnelReconciler) patchTunnelSecret(ctx context.Context, existingSecret *corev1.Secret, tunnelName, tunnelID string, credentials map[string]string) error {
	log := log.FromContext(ctx)
	
	// Get the operator pod to ensure ownership is maintained
	operatorPod := &corev1.Pod{}
	if err := r.Get(ctx, client.ObjectKey{Name: r.OperatorPodName, Namespace: r.Namespace}, operatorPod); err != nil {
		log.Error(err, "Failed to get operator pod for ownership", "podName", r.OperatorPodName)
		return fmt.Errorf("failed to get operator pod for ownership: %w", err)
	}
	
	// Update the secret data with new credentials
	existingSecret.Data["token"] = []byte(credentials["TunnelSecret"])
	existingSecret.Data["tunnel-id"] = []byte(tunnelID)
	existingSecret.Data["tunnel-name"] = []byte(tunnelName)
	existingSecret.Data["credentials"] = r.createCredentialsJSON(credentials)
	
	// Update labels
	if existingSecret.Labels == nil {
		existingSecret.Labels = make(map[string]string)
	}
	existingSecret.Labels["cloudflare.io/tunnel-name"] = tunnelName
	existingSecret.Labels["cloudflare.io/tunnel-id"] = tunnelID
	existingSecret.Labels["cloudflare.io/managed-by"] = "cloudflare-operator"
	
	// Ensure operator pod ownership is maintained
	existingSecret.OwnerReferences = []metav1.OwnerReference{
		{
			APIVersion: "v1",
			Kind:       "Pod",
			Name:       operatorPod.Name,
			UID:        operatorPod.UID,
			Controller: func() *bool { b := true; return &b }(),
		},
	}
	
	if err := r.Update(ctx, existingSecret); err != nil {
		return fmt.Errorf("failed to patch tunnel secret: %w", err)
	}
	
	log.Info("✅ Patched tunnel secret with new credentials and maintained ownership", "tunnelId", tunnelID, "ownerPod", operatorPod.Name)
	return nil
}

// handleTunnelDeletion handles the deletion of a tunnel secret with finalizer
func (r *TunnelReconciler) handleTunnelDeletion(ctx context.Context, tunnelSecret *corev1.Secret) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	
	// Check if our finalizer is present
	if !containsFinalizer(tunnelSecret.Finalizers, FinalizerTunnelCleanup) {
		log.Info("Finalizer not found on tunnel secret, skipping cleanup")
		return ctrl.Result{}, nil
	}
	
	// Extract tunnel ID from secret for cleanup
	tunnelIDBytes, ok := tunnelSecret.Data["tunnel-id"]
	if !ok || len(tunnelIDBytes) == 0 {
		log.Info("No tunnel ID found in secret being deleted")
		return r.removeFinalizer(ctx, tunnelSecret)
	}
	
	tunnelID := string(tunnelIDBytes)
	log.Info("🗑️  Processing tunnel deletion", "tunnelId", tunnelID)
	
	// Scale down cloudflared deployment first to disconnect active connections
	if err := r.scaleDownCloudflaredDeployment(ctx); err != nil {
		log.Error(err, "Failed to scale down cloudflared deployment during deletion")
		// Continue with cleanup even if scaling fails
	}
	
	// Delete tunnel from Cloudflare
	if err := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); err != nil {
		log.Error(err, "Failed to delete tunnel from Cloudflare", "tunnelId", tunnelID)
		return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
	}
	
	log.Info("✅ Successfully deleted tunnel from Cloudflare", "tunnelId", tunnelID)
	
	// Remove finalizer to allow secret deletion
	return r.removeFinalizer(ctx, tunnelSecret)
}

// removeFinalizer removes the tunnel cleanup finalizer from the secret
func (r *TunnelReconciler) removeFinalizer(ctx context.Context, secret *corev1.Secret) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	
	// Remove the finalizer
	secret.Finalizers = removeFinalizer(secret.Finalizers, FinalizerTunnelCleanup)
	
	if err := r.Update(ctx, secret); err != nil {
		log.Error(err, "Failed to remove finalizer from tunnel secret")
		return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
	}
	
	log.Info("✅ Removed finalizer from tunnel secret")
	return ctrl.Result{}, nil
}

// containsFinalizer checks if a finalizer is present in the slice
func containsFinalizer(finalizers []string, finalizer string) bool {
	for _, f := range finalizers {
		if f == finalizer {
			return true
		}
	}
	return false
}

// removeFinalizer removes a finalizer from the slice
func removeFinalizer(finalizers []string, finalizer string) []string {
	result := []string{}
	for _, f := range finalizers {
		if f != finalizer {
			result = append(result, f)
		}
	}
	return result
}

// CleanupTunnel deletes the tunnel when the operator is shutting down
func (r *TunnelReconciler) CleanupTunnel(ctx context.Context) error {
	if r.TunnelID == "" {
		return nil // No tunnel to clean up
	}

	log := log.FromContext(ctx)
	log.Info("Cleaning up operator tunnel", "tunnelId", r.TunnelID)

	// Delete the tunnel from Cloudflare
	if err := r.CloudflareClient.DeleteTunnel(ctx, r.TunnelID); err != nil {
		log.Error(err, "Failed to delete tunnel from Cloudflare", "tunnelId", r.TunnelID)
		return err
	}

	// Delete the tunnel secret
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cloudflare-operator-tunnel",
			Namespace: r.Namespace,
		},
	}
	if err := r.Delete(ctx, secret); err != nil && client.IgnoreNotFound(err) != nil {
		log.Error(err, "Failed to delete tunnel secret")
		return err
	}

	log.Info("✅ Tunnel cleanup complete", "tunnelId", r.TunnelID)
	r.TunnelID = ""
	return nil
}

// ensureSharedCloudflaredDeployment ensures the shared cloudflared deployment exists
func (r *TunnelReconciler) ensureSharedCloudflaredDeployment(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	deploymentName := "cloudflared"
	namespace := r.Namespace
	
	// Check if deployment already exists
	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      deploymentName,
		Namespace: namespace,
	}, deployment)
	
	if err == nil {
		// Deployment exists
		log.Info("Shared cloudflared deployment already exists", "name", deploymentName)
		return nil
	}
	
	if !errors.IsNotFound(err) {
		return fmt.Errorf("failed to get cloudflared deployment: %w", err)
	}
	
	// Create new deployment
	log.Info("Creating shared cloudflared deployment", "name", deploymentName)
	
	// First ensure we have a basic config
	if err := r.ensureCloudflaredConfig(ctx); err != nil {
		return fmt.Errorf("failed to ensure cloudflared config: %w", err)
	}
	
	// Get ConfigMap data for checksum calculation
	configMap := &corev1.ConfigMap{}
	if err := r.Get(ctx, client.ObjectKey{Name: "cloudflared-config", Namespace: namespace}, configMap); err != nil {
		return fmt.Errorf("failed to get cloudflared config for checksum: %w", err)
	}
	configChecksum := calculateConfigMapChecksum(configMap.Data["config.yaml"])
	
	replicas := int32(2)
	// Get tunnel secret to set as owner
	tunnelSecret := &corev1.Secret{}
	if err := r.Get(ctx, client.ObjectKey{Name: "cloudflare-operator-tunnel", Namespace: namespace}, tunnelSecret); err != nil {
		return fmt.Errorf("failed to get tunnel secret for owner reference: %w", err)
	}
	
	deployment = &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      deploymentName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":                          "cloudflared",
				"cloudflare.io/managed-by":     "cloudflare-operator",
			},
			OwnerReferences: []metav1.OwnerReference{
				{
					APIVersion: "v1",
					Kind:       "Secret",
					Name:       tunnelSecret.Name,
					UID:        tunnelSecret.UID,
					Controller: func() *bool { b := true; return &b }(),
				},
			},
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app": "cloudflared",
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app": "cloudflared",
					},
					Annotations: map[string]string{
						"cloudflare.io/config-checksum": configChecksum,
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  "cloudflared",
							Image: "cloudflare/cloudflared:latest",
							Args: []string{
								"tunnel",
								"--config",
								"/etc/cloudflared/config.yaml",
								"run",
							},
							Env: []corev1.EnvVar{
								{
									Name: "TUNNEL_CRED_CONTENTS",
									ValueFrom: &corev1.EnvVarSource{
										SecretKeyRef: &corev1.SecretKeySelector{
											LocalObjectReference: corev1.LocalObjectReference{
												Name: "cloudflare-operator-tunnel",
											},
											Key: "credentials",
										},
									},
								},
							},
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      "config",
									MountPath: "/etc/cloudflared",
									ReadOnly:  true,
								},
							},
							Resources: corev1.ResourceRequirements{
								Limits: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("100m"),
									corev1.ResourceMemory: resource.MustParse("128Mi"),
								},
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("50m"),
									corev1.ResourceMemory: resource.MustParse("64Mi"),
								},
							},
							SecurityContext: &corev1.SecurityContext{
								AllowPrivilegeEscalation: &[]bool{false}[0],
								Capabilities: &corev1.Capabilities{
									Drop: []corev1.Capability{"ALL"},
								},
								ReadOnlyRootFilesystem: &[]bool{true}[0],
								RunAsNonRoot:          &[]bool{true}[0],
								RunAsUser:             &[]int64{65532}[0],
							},
						},
					},
					Volumes: []corev1.Volume{
						{
							Name: "config",
							VolumeSource: corev1.VolumeSource{
								ConfigMap: &corev1.ConfigMapVolumeSource{
									LocalObjectReference: corev1.LocalObjectReference{
										Name: "cloudflared-config",
									},
								},
							},
						},
					},
				},
			},
		},
	}
	
	if err := r.Create(ctx, deployment); err != nil {
		return fmt.Errorf("failed to create cloudflared deployment: %w", err)
	}
	
	log.Info("✅ Created shared cloudflared deployment", "name", deploymentName)
	return nil
}

// ensureCloudflaredConfig creates a basic cloudflared config if it doesn't exist, or validates/updates existing one
func (r *TunnelReconciler) ensureCloudflaredConfig(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	// Get tunnel information from secret first
	tunnelSecret := &corev1.Secret{}
	if err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflare-operator-tunnel",
		Namespace: r.Namespace,
	}, tunnelSecret); err != nil {
		return fmt.Errorf("failed to get tunnel secret for config validation: %w", err)
	}
	
	currentTunnelID := string(tunnelSecret.Data["tunnel-id"])
	
	// Check if ConfigMap exists
	configMap := &corev1.ConfigMap{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflared-config",
		Namespace: r.Namespace,
	}, configMap)
	
	if err == nil {
		// ConfigMap exists - validate it has the correct tunnel ID
		if err := r.validateAndUpdateConfigMap(ctx, configMap, currentTunnelID); err != nil {
			log.Error(err, "Failed to validate/update ConfigMap", "tunnelId", currentTunnelID)
			return fmt.Errorf("failed to validate ConfigMap: %w", err)
		}
		return nil
	}
	
	if !errors.IsNotFound(err) {
		return fmt.Errorf("failed to get cloudflared config: %w", err)
	}
	
	// ConfigMap doesn't exist, create it
	tunnelID := currentTunnelID
	
	// Create basic config with just the catch-all rule
	basicConfig := fmt.Sprintf(`tunnel: %s
credentials-file: /dev/null

ingress:
- service: http_status:404
`, tunnelID)
	
	// Get tunnel secret for owner reference
	tunnelSecretForConfig := &corev1.Secret{}
	if err := r.Get(ctx, client.ObjectKey{Name: "cloudflare-operator-tunnel", Namespace: r.Namespace}, tunnelSecretForConfig); err != nil {
		return fmt.Errorf("failed to get tunnel secret for ConfigMap owner reference: %w", err)
	}
	
	// Create ConfigMap
	configMap = &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cloudflared-config",
			Namespace: r.Namespace,
			Labels: map[string]string{
				"app":                      "cloudflared",
				"cloudflare.io/managed-by": "cloudflare-operator",
			},
			OwnerReferences: []metav1.OwnerReference{
				{
					APIVersion: "v1",
					Kind:       "Secret",
					Name:       tunnelSecretForConfig.Name,
					UID:        tunnelSecretForConfig.UID,
					Controller: func() *bool { b := true; return &b }(),
				},
			},
		},
		Data: map[string]string{
			"config.yaml": basicConfig,
		},
	}
	
	if err := r.Create(ctx, configMap); err != nil {
		return fmt.Errorf("failed to create cloudflared config: %w", err)
	}
	
	log.Info("✅ Created basic cloudflared configuration")
	return nil
}

// createCredentialsJSON creates the credentials JSON that cloudflared expects
func (r *TunnelReconciler) createCredentialsJSON(credentials map[string]string) []byte {
	// Use the credentials map directly since it already has the correct format
	credentialsJSON, err := json.Marshal(credentials)
	if err != nil {
		// Return basic structure if marshaling fails
		return []byte(fmt.Sprintf(`{"AccountTag":"%s","TunnelSecret":"%s","TunnelID":"%s","Endpoint":"%s"}`, 
			credentials["AccountTag"], credentials["TunnelSecret"], credentials["TunnelID"], credentials["Endpoint"]))
	}
	
	return credentialsJSON
}

// validateAndUpdateConfigMap validates that ConfigMap has correct tunnel ID and updates if needed
func (r *TunnelReconciler) validateAndUpdateConfigMap(ctx context.Context, configMap *corev1.ConfigMap, expectedTunnelID string) error {
	log := log.FromContext(ctx)
	
	currentConfig := configMap.Data["config.yaml"]
	if currentConfig == "" {
		log.Info("ConfigMap missing config.yaml, will update", "expectedTunnelId", expectedTunnelID)
		return r.updateConfigMapTunnelID(ctx, configMap, expectedTunnelID)
	}
	
	// Extract current tunnel ID from config
	lines := strings.Split(currentConfig, "\n")
	var currentTunnelID string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "tunnel:") {
			parts := strings.Fields(line)
			if len(parts) >= 2 {
				currentTunnelID = parts[1]
				break
			}
		}
	}
	
	// Check if tunnel ID matches
	if currentTunnelID != expectedTunnelID {
		log.Info("ConfigMap has stale tunnel ID, updating", 
			"currentTunnelId", currentTunnelID, 
			"expectedTunnelId", expectedTunnelID)
		return r.updateConfigMapTunnelID(ctx, configMap, expectedTunnelID)
	}
	
	log.V(1).Info("ConfigMap tunnel ID is valid", "tunnelId", expectedTunnelID)
	return nil
}

// updateConfigMapTunnelID updates the ConfigMap with the correct tunnel ID
func (r *TunnelReconciler) updateConfigMapTunnelID(ctx context.Context, configMap *corev1.ConfigMap, tunnelID string) error {
	log := log.FromContext(ctx)
	
	// Create updated config
	updatedConfig := fmt.Sprintf(`tunnel: %s
credentials-file: /dev/null

ingress:
- service: http_status:404
`, tunnelID)
	
	// Update ConfigMap data
	if configMap.Data == nil {
		configMap.Data = make(map[string]string)
	}
	configMap.Data["config.yaml"] = updatedConfig
	
	// Update labels
	if configMap.Labels == nil {
		configMap.Labels = make(map[string]string)
	}
	configMap.Labels["app"] = "cloudflared"
	configMap.Labels["cloudflare.io/managed-by"] = "cloudflare-operator"
	configMap.Labels["cloudflare.io/tunnel-id"] = tunnelID
	
	if err := r.Update(ctx, configMap); err != nil {
		return fmt.Errorf("failed to update ConfigMap with tunnel ID: %w", err)
	}
	
	log.Info("✅ Updated ConfigMap with correct tunnel ID", "tunnelId", tunnelID)
	
	// Update deployment checksum to trigger pod rollout with new config
	if err := r.updateDeploymentConfigChecksum(ctx, tunnelID); err != nil {
		log.Error(err, "Failed to update deployment checksum after ConfigMap change")
		// Don't fail the whole operation, just log the error
	}
	
	return nil
}

// updateDeploymentConfigChecksum updates the deployment's config checksum to trigger pod rollout
func (r *TunnelReconciler) updateDeploymentConfigChecksum(ctx context.Context, tunnelID string) error {
	log := log.FromContext(ctx)
	
	// Get the cloudflared deployment
	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflared",
		Namespace: r.Namespace,
	}, deployment)
	
	if err != nil {
		if errors.IsNotFound(err) {
			// Deployment doesn't exist yet, this is fine
			return nil
		}
		return fmt.Errorf("failed to get cloudflared deployment: %w", err)
	}
	
	// Get updated ConfigMap to calculate new checksum
	configMap := &corev1.ConfigMap{}
	if err := r.Get(ctx, client.ObjectKey{Name: "cloudflared-config", Namespace: r.Namespace}, configMap); err != nil {
		return fmt.Errorf("failed to get ConfigMap for checksum calculation: %w", err)
	}
	
	newChecksum := calculateConfigMapChecksum(configMap.Data["config.yaml"])
	currentChecksum := deployment.Spec.Template.ObjectMeta.Annotations["cloudflare.io/config-checksum"]
	
	if currentChecksum != newChecksum {
		log.Info("ConfigMap changed, updating deployment checksum to trigger rollout", 
			"tunnelId", tunnelID, 
			"oldChecksum", currentChecksum, 
			"newChecksum", newChecksum)
		
		// Update deployment annotation to trigger rollout
		if deployment.Spec.Template.ObjectMeta.Annotations == nil {
			deployment.Spec.Template.ObjectMeta.Annotations = make(map[string]string)
		}
		deployment.Spec.Template.ObjectMeta.Annotations["cloudflare.io/config-checksum"] = newChecksum
		
		if err := r.Update(ctx, deployment); err != nil {
			return fmt.Errorf("failed to update deployment checksum: %w", err)
		}
		
		log.Info("✅ Updated deployment checksum, cloudflared pods will restart with new config")
	}
	
	return nil
}

// scaleDownCloudflaredDeployment scales the cloudflared deployment to 0 replicas to disconnect active connections
func (r *TunnelReconciler) scaleDownCloudflaredDeployment(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflared",
		Namespace: r.Namespace,
	}, deployment)
	
	if err != nil {
		if errors.IsNotFound(err) {
			// Deployment doesn't exist, nothing to scale down
			log.Info("Cloudflared deployment not found, skipping scale down")
			return nil
		}
		return fmt.Errorf("failed to get cloudflared deployment: %w", err)
	}
	
	// Check if already scaled down
	if deployment.Spec.Replicas != nil && *deployment.Spec.Replicas == 0 {
		log.Info("Cloudflared deployment already scaled down")
		return nil
	}
	
	// Scale down to 0 replicas
	replicas := int32(0)
	deployment.Spec.Replicas = &replicas
	
	if err := r.Update(ctx, deployment); err != nil {
		return fmt.Errorf("failed to scale down cloudflared deployment: %w", err)
	}
	
	log.Info("✅ Scaled down cloudflared deployment to disconnect tunnel connections")
	
	// Wait a moment for pods to terminate and connections to close
	time.Sleep(10 * time.Second)
	
	return nil
}

// EmergencyCleanup performs emergency tunnel cleanup during operator shutdown
func (r *TunnelReconciler) EmergencyCleanup(ctx context.Context) error {
	log := log.FromContext(ctx)
	log.Info("🚨 EMERGENCY CLEANUP: Starting emergency tunnel cleanup")

	// Get the tunnel secret from the operator's namespace
	tunnelSecret := &corev1.Secret{}
	secretName := "cloudflare-operator-tunnel"
	log.Info("🔍 EMERGENCY CLEANUP: Looking for tunnel secret", "secretName", secretName, "namespace", r.Namespace)
	
	err := r.Get(ctx, client.ObjectKey{Name: secretName, Namespace: r.Namespace}, tunnelSecret)
	
	if err != nil {
		if client.IgnoreNotFound(err) != nil {
			log.Error(err, "❌ EMERGENCY CLEANUP: Failed to get tunnel secret during emergency cleanup")
			return err
		}
		log.Info("ℹ️  EMERGENCY CLEANUP: Tunnel secret not found, nothing to clean up")
		return nil
	}

	// Extract tunnel ID from secret
	tunnelIDBytes, ok := tunnelSecret.Data["tunnel-id"]
	if !ok || len(tunnelIDBytes) == 0 {
		log.Info("ℹ️  EMERGENCY CLEANUP: No tunnel ID found in secret, skipping cleanup")
		return nil
	}
	
	tunnelID := string(tunnelIDBytes)
	log.Info("🎯 EMERGENCY CLEANUP: Found tunnel to clean up", "tunnelId", tunnelID)

	// Scale down cloudflared deployment first to disconnect active connections
	log.Info("📉 EMERGENCY CLEANUP: Scaling down cloudflared deployment")
	if err := r.scaleDownCloudflaredDeployment(ctx); err != nil {
		log.Error(err, "⚠️  EMERGENCY CLEANUP: Failed to scale down cloudflared deployment, continuing with cleanup")
	}

	// Delete tunnel from Cloudflare using existing retry logic
	log.Info("🗑️  EMERGENCY CLEANUP: Deleting tunnel from Cloudflare API", "tunnelId", tunnelID)
	if err := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); err != nil {
		log.Error(err, "❌ EMERGENCY CLEANUP: Failed to delete tunnel from Cloudflare during emergency cleanup", "tunnelId", tunnelID)
		return err
	}

	log.Info("✅ EMERGENCY CLEANUP: Emergency tunnel cleanup completed successfully", "tunnelId", tunnelID)
	return nil
}

// Cleanup job functions removed - cleanup now handled by SIGTERM handler

func (r *TunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Set up the controller to watch secrets (filtered in Reconcile function)
	return ctrl.NewControllerManagedBy(mgr).
		For(&corev1.Secret{}).
		Complete(r)
}