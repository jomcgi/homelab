package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cfapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
)

const (
	AnnotationHostname         = "cloudflare.io/hostname"
	AnnotationAccessEnabled    = "cloudflare.io/access-enabled"
	AnnotationAccessPolicy     = "cloudflare.io/access-policy"
	AnnotationAccessEmails     = "cloudflare.io/access-emails"
	AnnotationAccessProviders  = "cloudflare.io/access-providers"
	AnnotationTunnelName       = "cloudflare.io/tunnel-name"
	AnnotationZone             = "cloudflare.io/zone"
	AnnotationProxied          = "cloudflare.io/proxied"
	AnnotationAppID            = "cloudflare.io/app-id"
	AnnotationPolicyID         = "cloudflare.io/policy-id"
	
	FinalizerCloudflareCleanup = "cloudflare.io/cleanup"
)

type ServiceReconciler struct {
	client.Client
	Scheme           *runtime.Scheme
	CloudflareClient *cfapi.Client
}

func (r *ServiceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	var service corev1.Service
	if err := r.Get(ctx, req.NamespacedName, &service); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	hostname := service.Annotations[AnnotationHostname]
	if hostname == "" {
		return ctrl.Result{}, nil
	}

	// Handle deletion
	if service.DeletionTimestamp != nil {
		return r.handleDeletion(ctx, &service)
	}

	log.Info("Processing service with Cloudflare annotations", "hostname", hostname)

	// Add finalizer if not present
	if !containsString(service.Finalizers, FinalizerCloudflareCleanup) {
		service.Finalizers = append(service.Finalizers, FinalizerCloudflareCleanup)
		if err := r.Update(ctx, &service); err != nil {
			log.Error(err, "Failed to add finalizer")
			return ctrl.Result{}, err
		}
		return ctrl.Result{Requeue: true}, nil
	}

	accessEnabled := service.Annotations[AnnotationAccessEnabled] == "true"
	if accessEnabled {
		if err := r.handleZeroTrustApplication(ctx, &service); err != nil {
			log.Error(err, "Failed to handle Zero Trust application")
			return ctrl.Result{RequeueAfter: time.Minute * 5}, err
		}
	}

	tunnelName := service.Annotations[AnnotationTunnelName]
	if tunnelName != "" {
		if err := r.handleTunnel(ctx, &service); err != nil {
			log.Error(err, "Failed to handle tunnel")
			return ctrl.Result{RequeueAfter: time.Minute * 5}, err
		}
	}

	return ctrl.Result{}, nil
}

func (r *ServiceReconciler) handleZeroTrustApplication(ctx context.Context, service *corev1.Service) error {
	log := log.FromContext(ctx)
	
	hostname := service.Annotations[AnnotationHostname]
	policyRef := service.Annotations[AnnotationAccessPolicy]
	emailsAnnotation := service.Annotations[AnnotationAccessEmails]
	
	// Check if application already exists
	if appID := service.Annotations[AnnotationAppID]; appID != "" {
		log.Info("Zero Trust application already exists", "hostname", hostname, "appId", appID)
		return nil
	}

	var policyID string
	var emails []string

	// Option 1: Use pre-defined policy reference
	if policyRef != "" {
		log.Info("Using pre-defined policy", "hostname", hostname, "policyRef", policyRef)
		
		// Look up the policy ID from a ConfigMap or predefined mapping
		resolvedPolicyID, err := r.resolvePolicyReference(ctx, policyRef)
		if err != nil {
			return fmt.Errorf("failed to resolve policy reference '%s': %w", policyRef, err)
		}
		
		policyID = resolvedPolicyID
		log.Info("✅ Resolved policy reference", "hostname", hostname, "policyRef", policyRef, "policyId", policyID)

	} else if emailsAnnotation != "" {
		// Option 2: Create policy from direct email list
		log.Info("Creating policy from email list", "hostname", hostname)
		
		// Parse email list from JSON annotation
		if err := json.Unmarshal([]byte(emailsAnnotation), &emails); err != nil {
			return fmt.Errorf("failed to parse access emails: %w", err)
		}

		if len(emails) == 0 {
			return fmt.Errorf("at least one email is required for access policy")
		}

		// Create the access policy
		policyName := fmt.Sprintf("k8s-%s-policy", strings.ReplaceAll(hostname, ".", "-"))
		policy, err := r.CloudflareClient.CreateAccessPolicy(ctx, policyName, emails)
		if err != nil {
			log.Error(err, "Failed to create Cloudflare Access policy")
			return err
		}
		
		policyID = policy.ID
		log.Info("✅ Created Cloudflare Access policy", "hostname", hostname, "policyId", policy.ID, "policyName", policy.Name, "emails", emails)

	} else {
		return fmt.Errorf("either cloudflare.io/access-policy or cloudflare.io/access-emails is required when Zero Trust is enabled")
	}

	// Create the application linked to the policy
	appName := fmt.Sprintf("k8s-%s", strings.ReplaceAll(hostname, ".", "-"))
	app, err := r.CloudflareClient.CreateAccessApplication(ctx, hostname, appName, policyID)
	if err != nil {
		log.Error(err, "Failed to create Cloudflare Access application")
		// Clean up the policy if we created it and app creation fails
		if emailsAnnotation != "" || policyRef != "" {
			if err := r.CloudflareClient.DeleteAccessPolicy(ctx, policyID); err != nil {
				log.Error(err, "Failed to clean up access policy after app creation failure")
			}
		}
		return err
	}
	
	// Store IDs in annotations for cleanup
	if service.Annotations == nil {
		service.Annotations = make(map[string]string)
	}
	service.Annotations[AnnotationAppID] = app.ID
	
	// Store policy ID if we created it (either from emails or from policy template)
	if emailsAnnotation != "" || policyRef != "" {
		service.Annotations[AnnotationPolicyID] = policyID
	}
	
	if err := r.Update(ctx, service); err != nil {
		log.Error(err, "Failed to store IDs in annotations")
		// Clean up resources if annotation fails
		if err := r.CloudflareClient.DeleteAccessApplication(ctx, app.ID); err != nil {
			log.Error(err, "Failed to clean up access application after annotation failure")
		}
		if emailsAnnotation != "" || policyRef != "" {
			if err := r.CloudflareClient.DeleteAccessPolicy(ctx, policyID); err != nil {
				log.Error(err, "Failed to clean up access policy after annotation failure")
			}
		}
		return err
	}
	
	if policyRef != "" {
		log.Info("✅ Created Zero Trust application with pre-defined policy", "hostname", hostname, "appId", app.ID, "policyRef", policyRef)
	} else {
		log.Info("✅ Created complete Zero Trust setup", "hostname", hostname, "appId", app.ID, "policyId", policyID, "emails", emails)
	}
	
	return nil
}

func (r *ServiceReconciler) handleTunnel(ctx context.Context, service *corev1.Service) error {
	log := log.FromContext(ctx)
	
	log.Info("Updating shared cloudflared configuration", "service", service.Name)
	
	// Ensure shared cloudflared deployment exists
	if err := r.ensureSharedCloudflaredDeployment(ctx); err != nil {
		return fmt.Errorf("failed to ensure shared cloudflared deployment: %w", err)
	}
	
	// Update tunnel configuration with all annotated services
	if err := r.updateSharedTunnelConfiguration(ctx); err != nil {
		return fmt.Errorf("failed to update tunnel configuration: %w", err)
	}
	
	log.Info("✅ Shared cloudflared configuration updated")
	return nil
}

func (r *ServiceReconciler) handleDeletion(ctx context.Context, service *corev1.Service) (ctrl.Result, error) {
	log := log.FromContext(ctx)
	
	log.Info("Handling service deletion", "hostname", service.Annotations[AnnotationHostname])
	
	// Clean up Cloudflare application
	if appID := service.Annotations[AnnotationAppID]; appID != "" {
		log.Info("Deleting Cloudflare Access application", "appId", appID)
		if err := r.CloudflareClient.DeleteAccessApplication(ctx, appID); err != nil {
			log.Error(err, "Failed to delete Cloudflare Access application", "appId", appID)
			// Don't block deletion on cleanup failure, but log the error
		} else {
			log.Info("✅ Deleted Cloudflare Access application", "appId", appID)
		}
	}
	
	// Clean up Cloudflare policy
	if policyID := service.Annotations[AnnotationPolicyID]; policyID != "" {
		log.Info("Deleting Cloudflare Access policy", "policyId", policyID)
		if err := r.CloudflareClient.DeleteAccessPolicy(ctx, policyID); err != nil {
			log.Error(err, "Failed to delete Cloudflare Access policy", "policyId", policyID)
			// Don't block deletion on cleanup failure, but log the error
		} else {
			log.Info("✅ Deleted Cloudflare Access policy", "policyId", policyID)
		}
	}
	
	// TODO: Clean up tunnel resources when implemented
	
	// Remove finalizer to allow deletion
	service.Finalizers = removeString(service.Finalizers, FinalizerCloudflareCleanup)
	if err := r.Update(ctx, service); err != nil {
		log.Error(err, "Failed to remove finalizer")
		return ctrl.Result{}, err
	}
	
	log.Info("✅ Completed Cloudflare cleanup for service")
	
	// Update shared cloudflared configuration after deletion
	if err := r.updateSharedTunnelConfiguration(ctx); err != nil {
		log.Error(err, "Failed to update tunnel configuration after service deletion")
	}
	
	return ctrl.Result{}, nil
}

// Helper functions
func containsString(slice []string, s string) bool {
	for _, item := range slice {
		if item == s {
			return true
		}
	}
	return false
}

func removeString(slice []string, s string) []string {
	var result []string
	for _, item := range slice {
		if item != s {
			result = append(result, item)
		}
	}
	return result
}

// resolvePolicyReference resolves a policy reference name to create a new policy with predefined emails
func (r *ServiceReconciler) resolvePolicyReference(ctx context.Context, policyRef string) (string, error) {
	log := log.FromContext(ctx)
	
	// First try to find a ConfigMap with email templates
	configMap := &corev1.ConfigMap{}
	configMapKey := client.ObjectKey{
		Name:      "cloudflare-policy-templates",
		Namespace: "cloudflare-operator-system", // Default namespace for operator
	}
	
	var emails []string
	
	if err := r.Get(ctx, configMapKey, configMap); err == nil {
		// ConfigMap exists, look for the policy template
		if emailList, exists := configMap.Data[policyRef]; exists {
			log.Info("Found policy template in ConfigMap", "policyRef", policyRef, "emailList", emailList)
			if err := json.Unmarshal([]byte(emailList), &emails); err != nil {
				return "", fmt.Errorf("failed to parse email list for policy '%s': %w", policyRef, err)
			}
		}
	} else {
		log.Info("No cloudflare-policy-templates ConfigMap found, using hardcoded templates", "error", err.Error())
	}
	
	// Fallback to hardcoded email templates if not found in ConfigMap
	if len(emails) == 0 {
		hardcodedTemplates := map[string][]string{
			"personal-emails": {"joe.mcginley2@gmail.com", "joe@jomcgi.dev"},
			"team-emails":     {"team@jomcgi.dev", "admin@jomcgi.dev"},
			"admin-emails":    {"admin@jomcgi.dev"},
		}
		
		if templateEmails, exists := hardcodedTemplates[policyRef]; exists {
			emails = templateEmails
			log.Info("Found policy template in hardcoded mappings", "policyRef", policyRef, "emails", emails)
		} else {
			return "", fmt.Errorf("policy template '%s' not found in ConfigMap or hardcoded templates", policyRef)
		}
	}
	
	if len(emails) == 0 {
		return "", fmt.Errorf("no emails found for policy template '%s'", policyRef)
	}
	
	// Create the policy using the template emails
	policyName := fmt.Sprintf("k8s-template-%s", policyRef)
	policy, err := r.CloudflareClient.CreateAccessPolicy(ctx, policyName, emails)
	if err != nil {
		return "", fmt.Errorf("failed to create policy from template '%s': %w", policyRef, err)
	}
	
	log.Info("✅ Created policy from template", "policyRef", policyRef, "policyId", policy.ID, "emails", emails)
	return policy.ID, nil
}

func (r *ServiceReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&corev1.Service{}).
		Complete(r)
}