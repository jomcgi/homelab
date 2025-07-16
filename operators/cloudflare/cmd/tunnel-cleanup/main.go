package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"

	cfapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
)

const (
	FinalizerTunnelCleanup = "cloudflare.io/tunnel-cleanup"
)

func main() {
	log.Println("🚀 Starting standalone tunnel cleanup job")

	// Get required environment variables
	tunnelSecretName := os.Getenv("TUNNEL_SECRET_NAME")
	namespace := os.Getenv("NAMESPACE")
	if tunnelSecretName == "" || namespace == "" {
		log.Fatal("TUNNEL_SECRET_NAME and NAMESPACE environment variables are required")
	}

	// Initialize Kubernetes client
	config, err := rest.InClusterConfig()
	if err != nil {
		log.Fatalf("Failed to create in-cluster config: %v", err)
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		log.Fatalf("Failed to create Kubernetes clientset: %v", err)
	}

	// Initialize Cloudflare client
	cfClient, err := cfapi.NewClient()
	if err != nil {
		log.Fatalf("Failed to create Cloudflare client: %v", err)
	}

	log.Printf("👀 Watching for deletion of tunnel secret: %s/%s", namespace, tunnelSecretName)

	// Watch for tunnel secret deletion
	ctx := context.Background()
	for {
		secret, err := clientset.CoreV1().Secrets(namespace).Get(ctx, tunnelSecretName, metav1.GetOptions{})
		if err != nil {
			log.Printf("Secret %s not found, job complete", tunnelSecretName)
			return
		}

		// Check if secret is being deleted
		if secret.DeletionTimestamp != nil {
			log.Printf("🔥 Secret %s is being deleted, starting cleanup", tunnelSecretName)
			
			if err := performTunnelCleanup(ctx, cfClient, secret); err != nil {
				log.Printf("❌ Cleanup failed: %v", err)
				// Continue retrying - don't exit on failure
				time.Sleep(30 * time.Second)
				continue
			}

			// Remove finalizer after successful cleanup
			if err := removeFinalizer(ctx, clientset, secret); err != nil {
				log.Printf("❌ Failed to remove finalizer: %v", err)
				time.Sleep(10 * time.Second)
				continue
			}

			log.Println("✅ Tunnel cleanup complete, job exiting")
			return
		}

		// Secret exists but not being deleted, wait and check again
		time.Sleep(10 * time.Second)
	}
}

func performTunnelCleanup(ctx context.Context, cfClient *cfapi.Client, secret *corev1.Secret) error {
	// Extract tunnel ID from secret
	tunnelIDBytes, exists := secret.Data["tunnel-id"]
	if !exists {
		log.Println("No tunnel ID found in secret, skipping tunnel cleanup")
		return nil
	}

	tunnelID := string(tunnelIDBytes)
	log.Printf("🚮 Deleting Cloudflare tunnel: %s", tunnelID)

	// Use the enhanced DeleteTunnel with retry logic
	if err := cfClient.DeleteTunnel(ctx, tunnelID); err != nil {
		return fmt.Errorf("failed to delete tunnel %s: %w", tunnelID, err)
	}

	log.Printf("✅ Successfully deleted Cloudflare tunnel: %s", tunnelID)
	return nil
}

func removeFinalizer(ctx context.Context, clientset *kubernetes.Clientset, secret *corev1.Secret) error {
	// Get the latest version of the secret
	latestSecret, err := clientset.CoreV1().Secrets(secret.Namespace).Get(ctx, secret.Name, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("failed to get latest secret: %w", err)
	}

	// Remove the finalizer
	var newFinalizers []string
	for _, finalizer := range latestSecret.Finalizers {
		if finalizer != FinalizerTunnelCleanup {
			newFinalizers = append(newFinalizers, finalizer)
		}
	}

	latestSecret.Finalizers = newFinalizers

	// Update the secret
	_, err = clientset.CoreV1().Secrets(secret.Namespace).Update(ctx, latestSecret, metav1.UpdateOptions{})
	if err != nil {
		return fmt.Errorf("failed to update secret finalizers: %w", err)
	}

	log.Printf("✅ Removed finalizer from secret: %s", secret.Name)
	return nil
}