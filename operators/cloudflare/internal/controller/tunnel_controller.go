package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cfapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
)

const (
	FinalizerTunnelCleanup = "cloudflare.io/tunnel-cleanup"
	TunnelSecretName       = "cloudflare-operator-tunnel"
)

type TunnelReconciler struct {
	client.Client
	Scheme           *runtime.Scheme
	CloudflareClient *cfapi.Client
	Namespace        string
	OperatorPodName  string
	
	// Use mutex for thread-safe access to tunnel ID
	mu       sync.RWMutex
	tunnelID string
}

// GetTunnelID safely returns the current tunnel ID
func (r *TunnelReconciler) GetTunnelID() string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.tunnelID
}

// SetTunnelID safely sets the tunnel ID
func (r *TunnelReconciler) SetTunnelID(id string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.tunnelID = id
}

func (r *TunnelReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Handle initialization request
	if req.Name == "" && req.Namespace == "" {
		return r.initializeTunnel(ctx)
	}

	// Only process our tunnel secret
	if req.Name != TunnelSecretName || req.Namespace != r.Namespace {
		return ctrl.Result{}, nil
	}

	// Get the tunnel secret
	tunnelSecret := &corev1.Secret{}
	err := r.Get(ctx, client.ObjectKey{Name: TunnelSecretName, Namespace: r.Namespace}, tunnelSecret)
	
	if err != nil {
		if errors.IsNotFound(err) {
			log.Info("Tunnel secret not found, will create new tunnel")
			return r.createTunnel(ctx)
		}
		return ctrl.Result{}, err
	}

	// Handle deletion
	if !tunnelSecret.DeletionTimestamp.IsZero() {
		return r.handleDeletion(ctx, tunnelSecret)
	}

	// Ensure finalizer is present
	if !controllerutil.ContainsFinalizer(tunnelSecret, FinalizerTunnelCleanup) {
		controllerutil.AddFinalizer(tunnelSecret, FinalizerTunnelCleanup)
		if err := r.Update(ctx, tunnelSecret); err != nil {
			return ctrl.Result{}, err
		}
	}

	// Validate existing tunnel
	return r.validateTunnel(ctx, tunnelSecret)
}

func (r *TunnelReconciler) initializeTunnel(ctx context.Context) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	log.Info("Initializing operator tunnel")

	// Check if tunnel already exists
	tunnelSecret := &corev1.Secret{}
	err := r.Get(ctx, client.ObjectKey{Name: TunnelSecretName, Namespace: r.Namespace}, tunnelSecret)
	
	if err == nil {
		// Tunnel exists, validate it
		return r.validateTunnel(ctx, tunnelSecret)
	}

	if !errors.IsNotFound(err) {
		return ctrl.Result{}, err
	}

	// Create new tunnel
	return r.createTunnel(ctx)
}

func (r *TunnelReconciler) createTunnel(ctx context.Context) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Generate unique tunnel name
	tunnelName := fmt.Sprintf("k8s-operator-%s-%d", r.Namespace, time.Now().Unix())
	
	log.Info("Creating Cloudflare tunnel", "name", tunnelName)
	
	tunnel, err := r.CloudflareClient.CreateTunnel(ctx, tunnelName)
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Minute}, fmt.Errorf("failed to create tunnel: %w", err)
	}

	// Get tunnel credentials
	credentials, err := r.CloudflareClient.GetTunnelCredentials(ctx, tunnel.ID)
	if err != nil {
		// Clean up tunnel on failure
		if delErr := r.CloudflareClient.DeleteTunnel(ctx, tunnel.ID); delErr != nil {
			log.Error(delErr, "Failed to cleanup tunnel after credentials error")
		}
		return ctrl.Result{RequeueAfter: time.Minute}, fmt.Errorf("failed to get credentials: %w", err)
	}

	// Create tunnel secret
	if err := r.createTunnelSecret(ctx, tunnelName, tunnel.ID, credentials); err != nil {
		// Clean up tunnel on failure
		if delErr := r.CloudflareClient.DeleteTunnel(ctx, tunnel.ID); delErr != nil {
			log.Error(delErr, "Failed to cleanup tunnel after secret error")
		}
		return ctrl.Result{RequeueAfter: time.Minute}, err
	}

	// Store tunnel ID
	r.SetTunnelID(tunnel.ID)

	// Create cloudflared deployment
	if err := r.ensureCloudflaredDeployment(ctx); err != nil {
		log.Error(err, "Failed to create cloudflared deployment")
		return ctrl.Result{RequeueAfter: time.Minute}, nil
	}

	log.Info("✅ Tunnel created successfully", "tunnelId", tunnel.ID)
	return ctrl.Result{RequeueAfter: 10 * time.Minute}, nil
}

func (r *TunnelReconciler) validateTunnel(ctx context.Context, tunnelSecret *corev1.Secret) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	tunnelID := string(tunnelSecret.Data["tunnel-id"])
	if tunnelID == "" {
		log.Info("Invalid tunnel secret, missing tunnel ID")
		return r.replaceTunnel(ctx, tunnelSecret)
	}

	// Validate tunnel exists in Cloudflare
	if err := r.CloudflareClient.ValidateExistingTunnel(ctx, tunnelID); err != nil {
		log.Info("Tunnel validation failed", "tunnelId", tunnelID, "error", err.Error())
		return r.replaceTunnel(ctx, tunnelSecret)
	}

	// Store tunnel ID
	r.SetTunnelID(tunnelID)

	// Ensure cloudflared deployment exists
	if err := r.ensureCloudflaredDeployment(ctx); err != nil {
		log.Error(err, "Failed to ensure cloudflared deployment")
		return ctrl.Result{RequeueAfter: time.Minute}, nil
	}

	log.V(1).Info("Tunnel validated", "tunnelId", tunnelID)
	return ctrl.Result{RequeueAfter: 10 * time.Minute}, nil
}

func (r *TunnelReconciler) replaceTunnel(ctx context.Context, oldSecret *corev1.Secret) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	log.Info("Replacing invalid tunnel")

	// Delete old secret (will trigger cleanup via finalizer)
	if err := r.Delete(ctx, oldSecret); err != nil {
		return ctrl.Result{}, err
	}

	// Requeue to create new tunnel
	return ctrl.Result{Requeue: true}, nil
}

func (r *TunnelReconciler) handleDeletion(ctx context.Context, tunnelSecret *corev1.Secret) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Check if our finalizer is present
	if !controllerutil.ContainsFinalizer(tunnelSecret, FinalizerTunnelCleanup) {
		return ctrl.Result{}, nil
	}

	tunnelID := string(tunnelSecret.Data["tunnel-id"])
	if tunnelID != "" {
		log.Info("Deleting tunnel from Cloudflare", "tunnelId", tunnelID)
		
		// Scale down cloudflared first
		if err := r.scaleDownCloudflaredDeployment(ctx); err != nil {
			log.Error(err, "Failed to scale down cloudflared")
			// Continue with deletion
		}

		// Delete tunnel with retry logic
		if err := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); err != nil {
			log.Error(err, "Failed to delete tunnel")
			return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
		}

		log.Info("✅ Tunnel deleted from Cloudflare", "tunnelId", tunnelID)
	}

	// Remove finalizer
	controllerutil.RemoveFinalizer(tunnelSecret, FinalizerTunnelCleanup)
	if err := r.Update(ctx, tunnelSecret); err != nil {
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

func (r *TunnelReconciler) createTunnelSecret(ctx context.Context, tunnelName, tunnelID string, credentials map[string]string) error {
	log := log.FromContext(ctx)

	credentialsJSON, err := json.Marshal(credentials)
	if err != nil {
		return fmt.Errorf("failed to marshal credentials: %w", err)
	}

	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      TunnelSecretName,
			Namespace: r.Namespace,
			Labels: map[string]string{
				"app":                       "cloudflare-operator",
				"cloudflare.io/tunnel-name": tunnelName,
				"cloudflare.io/tunnel-id":   tunnelID,
			},
			Finalizers: []string{FinalizerTunnelCleanup},
		},
		Type: corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			"token":       []byte(credentials["TunnelSecret"]),
			"tunnel-id":   []byte(tunnelID),
			"tunnel-name": []byte(tunnelName),
			"credentials": credentialsJSON,
		},
	}

	// Set operator pod as owner if possible
	operatorPod := &corev1.Pod{}
	if err := r.Get(ctx, client.ObjectKey{Name: r.OperatorPodName, Namespace: r.Namespace}, operatorPod); err == nil {
		if err := controllerutil.SetControllerReference(operatorPod, secret, r.Scheme); err != nil {
			log.Error(err, "Failed to set owner reference")
		}
	}

	if err := r.Create(ctx, secret); err != nil {
		return fmt.Errorf("failed to create tunnel secret: %w", err)
	}

	log.Info("Created tunnel secret", "name", TunnelSecretName)
	return nil
}

// EmergencyCleanup performs best-effort cleanup during shutdown
func (r *TunnelReconciler) EmergencyCleanup(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	tunnelID := r.GetTunnelID()
	if tunnelID == "" {
		// Try to get from secret
		secret := &corev1.Secret{}
		if err := r.Get(ctx, client.ObjectKey{Name: TunnelSecretName, Namespace: r.Namespace}, secret); err == nil {
			tunnelID = string(secret.Data["tunnel-id"])
		}
	}

	if tunnelID == "" {
		log.Info("No tunnel ID found for cleanup")
		return nil
	}

	log.Info("🚨 Performing emergency cleanup", "tunnelId", tunnelID)

	// Best effort - scale down cloudflared
	if err := r.scaleDownCloudflaredDeployment(ctx); err != nil {
		log.Error(err, "Failed to scale down cloudflared during emergency cleanup")
	}

	// Delete tunnel from Cloudflare
	if err := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); err != nil {
		return fmt.Errorf("failed to delete tunnel %s: %w", tunnelID, err)
	}

	log.Info("✅ Emergency cleanup completed", "tunnelId", tunnelID)
	return nil
}

func (r *TunnelReconciler) ensureCloudflaredDeployment(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	// Get the tunnel secret for credentials
	tunnelSecret := &corev1.Secret{}
	if err := r.Get(ctx, client.ObjectKey{Name: TunnelSecretName, Namespace: r.Namespace}, tunnelSecret); err != nil {
		return fmt.Errorf("failed to get tunnel secret: %w", err)
	}
	
	tunnelID := string(tunnelSecret.Data["tunnel-id"])
	if tunnelID == "" {
		return fmt.Errorf("tunnel ID not found in secret")
	}
	
	// Check if deployment already exists
	existingDeployment := &appsv1.Deployment{}
	err := r.Get(ctx, client.ObjectKey{Name: "cloudflared", Namespace: r.Namespace}, existingDeployment)
	
	if err == nil {
		// Deployment exists, check if it needs updating
		log.V(1).Info("Cloudflared deployment already exists", "tunnelId", tunnelID)
		return nil
	}
	
	if !errors.IsNotFound(err) {
		return fmt.Errorf("failed to check existing deployment: %w", err)
	}
	
	// Create new deployment
	deployment := r.createCloudflaredDeployment(tunnelSecret)
	
	// Set controller reference
	if err := controllerutil.SetControllerReference(tunnelSecret, deployment, r.Scheme); err != nil {
		return fmt.Errorf("failed to set controller reference: %w", err)
	}
	
	if err := r.Create(ctx, deployment); err != nil {
		return fmt.Errorf("failed to create cloudflared deployment: %w", err)
	}
	
	log.Info("Created cloudflared deployment", "tunnelId", tunnelID)
	return nil
}

func (r *TunnelReconciler) createCloudflaredDeployment(tunnelSecret *corev1.Secret) *appsv1.Deployment {
	tunnelID := string(tunnelSecret.Data["tunnel-id"])
	
	// Create checksum of tunnel secret for restart annotation
	checksum := fmt.Sprintf("%x", tunnelSecret.Data)
	
	replicas := int32(1)
	
	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cloudflared",
			Namespace: r.Namespace,
			Labels: map[string]string{
				"app":                       "cloudflared",
				"cloudflare.io/tunnel-id":   tunnelID,
				"cloudflare.io/managed-by":  "cloudflare-operator",
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
						"app":                       "cloudflared",
						"cloudflare.io/tunnel-id":   tunnelID,
						"cloudflare.io/managed-by":  "cloudflare-operator",
					},
					Annotations: map[string]string{
						// Force restart when tunnel secret changes
						"checksum/tunnel-secret": checksum,
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  "cloudflared",
							Image: "cloudflare/cloudflared:latest",
							Args: []string{
								"tunnel",
								"--no-autoupdate",
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
												Name: TunnelSecretName,
											},
											Key: "token",
										},
									},
								},
							},
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("10m"),
									corev1.ResourceMemory: resource.MustParse("32Mi"),
								},
								Limits: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("100m"),
									corev1.ResourceMemory: resource.MustParse("128Mi"),
								},
							},
						},
					},
				},
			},
		},
	}
	
	return deployment
}

func (r *TunnelReconciler) scaleDownCloudflaredDeployment(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflared",
		Namespace: r.Namespace,
	}, deployment)
	
	if err != nil {
		if errors.IsNotFound(err) {
			return nil
		}
		return err
	}

	if deployment.Spec.Replicas != nil && *deployment.Spec.Replicas == 0 {
		return nil
	}

	replicas := int32(0)
	deployment.Spec.Replicas = &replicas
	
	if err := r.Update(ctx, deployment); err != nil {
		return err
	}

	log.Info("Scaled down cloudflared deployment")
	
	// Give pods time to terminate
	time.Sleep(5 * time.Second)
	
	return nil
}

func (r *TunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&corev1.Secret{}).
		Complete(r)
}