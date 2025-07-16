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
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/api/resource"
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

// ensureSharedCloudflaredDeployment ensures the shared cloudflared deployment exists
func (r *ServiceReconciler) ensureSharedCloudflaredDeployment(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	deploymentName := "cloudflared"
	namespace := "default" // TODO: make this configurable
	
	// Check if deployment already exists
	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      deploymentName,
		Namespace: namespace,
	}, deployment)
	
	if err == nil {
		// Deployment exists, check if it needs updates
		log.Info("Shared cloudflared deployment already exists", "name", deploymentName)
		return r.updateCloudflaredDeployment(ctx, deployment)
	}
	
	if !errors.IsNotFound(err) {
		return fmt.Errorf("failed to get cloudflared deployment: %w", err)
	}
	
	// Create new deployment
	log.Info("Creating shared cloudflared deployment", "name", deploymentName)
	
	// Get ConfigMap data for checksum calculation
	configMap := &corev1.ConfigMap{}
	if err := r.Get(ctx, client.ObjectKey{Name: "cloudflared-config", Namespace: namespace}, configMap); err != nil {
		return fmt.Errorf("failed to get cloudflared config for checksum: %w", err)
	}
	configChecksum := calculateConfigMapChecksum(configMap.Data["config.yaml"])
	
	replicas := int32(2)
	deployment = &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      deploymentName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":                          "cloudflared",
				"cloudflare.io/managed-by":     "cloudflare-operator",
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
									Name: "TUNNEL_TOKEN",
									ValueFrom: &corev1.EnvVarSource{
										SecretKeyRef: &corev1.SecretKeySelector{
											LocalObjectReference: corev1.LocalObjectReference{
												Name: "cloudflare-operator-tunnel",
											},
											Key: "token",
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

// updateCloudflaredDeployment updates the cloudflared deployment if needed
func (r *ServiceReconciler) updateCloudflaredDeployment(ctx context.Context, deployment *appsv1.Deployment) error {
	log := log.FromContext(ctx)
	
	// Get current ConfigMap to calculate checksum
	configMap := &corev1.ConfigMap{}
	if err := r.Get(ctx, client.ObjectKey{Name: "cloudflared-config", Namespace: deployment.Namespace}, configMap); err != nil {
		return fmt.Errorf("failed to get cloudflared config for checksum: %w", err)
	}
	
	newChecksum := calculateConfigMapChecksum(configMap.Data["config.yaml"])
	currentChecksum := deployment.Spec.Template.ObjectMeta.Annotations["cloudflare.io/config-checksum"]
	
	// If checksum changed, update the deployment to trigger rollout
	if currentChecksum != newChecksum {
		log.Info("ConfigMap changed, updating deployment to trigger rollout", 
			"name", deployment.Name, 
			"oldChecksum", currentChecksum, 
			"newChecksum", newChecksum)
		
		if deployment.Spec.Template.ObjectMeta.Annotations == nil {
			deployment.Spec.Template.ObjectMeta.Annotations = make(map[string]string)
		}
		deployment.Spec.Template.ObjectMeta.Annotations["cloudflare.io/config-checksum"] = newChecksum
		
		return r.Update(ctx, deployment)
	}
	
	log.Info("Cloudflared deployment is up to date", "name", deployment.Name)
	return nil
}

// updateSharedTunnelConfiguration updates the tunnel configuration with all annotated services
func (r *ServiceReconciler) updateSharedTunnelConfiguration(ctx context.Context) error {
	log := log.FromContext(ctx)
	
	// Get all services with cloudflare annotations
	serviceList := &corev1.ServiceList{}
	if err := r.List(ctx, serviceList); err != nil {
		return fmt.Errorf("failed to list services: %w", err)
	}
	
	// Build ingress rules from annotated services
	var ingressRules []map[string]interface{}
	
	for _, service := range serviceList.Items {
		hostname, hasHostname := service.Annotations[AnnotationHostname]
		if !hasHostname {
			continue
		}
		
		// Build service URL
		serviceURL := fmt.Sprintf("http://%s.%s.svc.cluster.local:%d", 
			service.Name, service.Namespace, service.Spec.Ports[0].Port)
		
		rule := map[string]interface{}{
			"hostname": hostname,
			"service":  serviceURL,
		}
		
		ingressRules = append(ingressRules, rule)
		log.Info("Added ingress rule", "hostname", hostname, "service", serviceURL)
	}
	
	// Add catch-all rule
	ingressRules = append(ingressRules, map[string]interface{}{
		"service": "http_status:404",
	})
	
	// Get tunnel information from secret
	tunnelSecret := &corev1.Secret{}
	if err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflare-operator-tunnel",
		Namespace: "default",
	}, tunnelSecret); err != nil {
		return fmt.Errorf("failed to get tunnel secret: %w", err)
	}
	
	tunnelID := string(tunnelSecret.Data["tunnel-id"])
	
	// Create tunnel configuration
	config := map[string]interface{}{
		"tunnel":           tunnelID,
		"credentials-file": "/dev/null", // Use TUNNEL_TOKEN instead
		"ingress":          ingressRules,
	}
	
	// Create or update ConfigMap
	configMap := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cloudflared-config",
			Namespace: "default",
			Labels: map[string]string{
				"app":                      "cloudflared",
				"cloudflare.io/managed-by": "cloudflare-operator",
			},
		},
		Data: map[string]string{
			"config.yaml": r.marshalYAML(config),
		},
	}
	
	// Check if ConfigMap exists
	existingConfigMap := &corev1.ConfigMap{}
	err := r.Get(ctx, client.ObjectKey{
		Name:      "cloudflared-config",
		Namespace: "default",
	}, existingConfigMap)
	
	if errors.IsNotFound(err) {
		// Create new ConfigMap
		if err := r.Create(ctx, configMap); err != nil {
			return fmt.Errorf("failed to create cloudflared config: %w", err)
		}
		log.Info("✅ Created cloudflared configuration", "rules", len(ingressRules)-1)
	} else if err != nil {
		return fmt.Errorf("failed to get existing config: %w", err)
	} else {
		// Update existing ConfigMap
		existingConfigMap.Data = configMap.Data
		if err := r.Update(ctx, existingConfigMap); err != nil {
			return fmt.Errorf("failed to update cloudflared config: %w", err)
		}
		log.Info("✅ Updated cloudflared configuration", "rules", len(ingressRules)-1)
	}
	
	return nil
}

// marshalYAML converts a map to YAML string (simple implementation)
func (r *ServiceReconciler) marshalYAML(data map[string]interface{}) string {
	// Simple YAML marshaling for our use case
	yaml := ""
	
	if tunnel, ok := data["tunnel"].(string); ok {
		yaml += fmt.Sprintf("tunnel: %s\n", tunnel)
	}
	
	if credsFile, ok := data["credentials-file"].(string); ok {
		yaml += fmt.Sprintf("credentials-file: %s\n", credsFile)
	}
	
	yaml += "\ningress:\n"
	
	if ingress, ok := data["ingress"].([]map[string]interface{}); ok {
		for _, rule := range ingress {
			if hostname, hasHostname := rule["hostname"].(string); hasHostname {
				yaml += fmt.Sprintf("- hostname: %s\n", hostname)
				yaml += fmt.Sprintf("  service: %s\n", rule["service"])
			} else {
				yaml += fmt.Sprintf("- service: %s\n", rule["service"])
			}
		}
	}
	
	return yaml
}

func (r *ServiceReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&corev1.Service{}).
		Complete(r)
}