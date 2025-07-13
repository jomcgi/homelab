package controller

import (
	"context"
	"fmt"
	"os"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cfapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
)

type TunnelReconciler struct {
	client.Client
	Scheme           *runtime.Scheme
	CloudflareClient *cfapi.Client
	TunnelID         string // Current tunnel ID managed by this operator instance
}

func (r *TunnelReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// This controller manages a single shared tunnel for the operator instance
	// The tunnel is created when the operator starts and deleted when it's removed
	
	// Check if we already have a tunnel secret
	tunnelSecret := &corev1.Secret{}
	secretName := "cloudflare-operator-tunnel"
	err := r.Get(ctx, client.ObjectKey{Name: secretName, Namespace: "default"}, tunnelSecret)
	
	if err != nil {
		if client.IgnoreNotFound(err) != nil {
			log.Error(err, "Failed to get tunnel secret")
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}
		
		// Secret doesn't exist, create a new tunnel
		operatorNamespace := os.Getenv("NAMESPACE")
		if operatorNamespace == "" {
			operatorNamespace = "default"
		}
		
		// Generate a unique tunnel name based on namespace and timestamp
		tunnelName := fmt.Sprintf("k8s-operator-%s-%d", operatorNamespace, time.Now().Unix())
		
		log.Info("Creating operator-managed Cloudflare tunnel", "name", tunnelName)
		
		tunnel, err := r.CloudflareClient.CreateTunnel(ctx, tunnelName)
		if err != nil {
			log.Error(err, "Failed to create tunnel")
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}

		tunnelID := tunnel.ID
		log.Info("✅ Created Cloudflare tunnel", "tunnelId", tunnelID, "name", tunnelName)

		// Get tunnel token for deployment
		token, err := r.CloudflareClient.GetTunnelToken(ctx, tunnelID)
		if err != nil {
			log.Error(err, "Failed to get tunnel token", "tunnelId", tunnelID)
			// Clean up the tunnel since we can't use it without a token
			if deleteErr := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); deleteErr != nil {
				log.Error(deleteErr, "Failed to delete tunnel after token error", "tunnelId", tunnelID)
			}
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}

		// Store the tunnel info in a secret
		if err := r.createTunnelSecret(ctx, tunnelName, tunnelID, token); err != nil {
			log.Error(err, "Failed to create tunnel secret")
			// Clean up the tunnel since we can't store its credentials
			if deleteErr := r.CloudflareClient.DeleteTunnel(ctx, tunnelID); deleteErr != nil {
				log.Error(deleteErr, "Failed to delete tunnel after secret error", "tunnelId", tunnelID)
			}
			return ctrl.Result{RequeueAfter: time.Minute * 1}, nil
		}

		log.Info("✅ Operator tunnel setup complete", "tunnelId", tunnelID)
		
		// Store tunnel ID in memory for cleanup on shutdown
		r.TunnelID = tunnelID
	} else {
		// Tunnel secret exists, extract tunnel ID
		if tunnelIDBytes, ok := tunnelSecret.Data["tunnel-id"]; ok {
			r.TunnelID = string(tunnelIDBytes)
			log.V(1).Info("Operator tunnel already configured", "tunnelId", r.TunnelID)
		}
	}

	return ctrl.Result{RequeueAfter: time.Minute * 10}, nil
}

// createTunnelSecret creates a Kubernetes secret containing the tunnel token
func (r *TunnelReconciler) createTunnelSecret(ctx context.Context, tunnelName, tunnelID, token string) error {
	log := log.FromContext(ctx)
	
	secretName := "cloudflare-operator-tunnel"
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      secretName,
			Namespace: "default", // Use same namespace as operator for now
			Labels: map[string]string{
				"app":                          "cloudflare-operator",
				"cloudflare.io/tunnel-name":    tunnelName,
				"cloudflare.io/tunnel-id":      tunnelID,
				"cloudflare.io/managed-by":     "cloudflare-operator",
			},
		},
		Type: corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			"token":       []byte(token),
			"tunnel-id":   []byte(tunnelID),
			"tunnel-name": []byte(tunnelName),
		},
	}

	if err := r.Create(ctx, secret); err != nil {
		return fmt.Errorf("failed to create tunnel secret: %w", err)
	}

	log.Info("✅ Created tunnel secret", "secretName", secretName, "tunnelId", tunnelID)
	return nil
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
			Namespace: "default",
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

func (r *TunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// This would be uncommented when we have the actual CRD type
	// return ctrl.NewControllerManagedBy(mgr).
	// 	For(&cloudflareapi.Tunnel{}).
	// 	Complete(r)
	return nil
}