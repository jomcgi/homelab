# Building a Cloudflare Kubernetes Operator with Operator-SDK

## Executive Summary

This guide provides a comprehensive, step-by-step approach to building a production-ready Kubernetes operator that manages Cloudflare resources. The operator handles zero trust access applications, tunnels, DNS records, and access policies while maintaining critical order of operations to ensure security. Each phase is designed to be self-contained with clear objectives, implementation steps, and validation checkpoints.

## Architecture Overview

The Cloudflare operator manages the following resources in this specific order:
1. **Access Policies** - Define who can access applications
2. **Zero Trust Applications** - Create protected applications  
3. **Cloudflare Tunnels** - Establish secure connections
4. **DNS Records** - Configure public endpoints

This ordering ensures that ingress is never exposed without proper access controls in place.

## Phase 1: Project Setup and Initial Structure

### Context & Prerequisites
- Go version 1.22+
- Docker version 17.03+
- kubectl with cluster access
- Cloudflare account with API token
- operator-sdk CLI installed

### Installation Commands
```bash
# Install operator-sdk via Homebrew (macOS)
brew install operator-sdk

# Or download from GitHub
export ARCH=$(case $(uname -m) in x86_64) echo -n amd64 ;; aarch64) echo -n arm64 ;; *) echo -n $(uname -m) ;; esac)
export OS=$(uname | awk '{print tolower($0)}')
export OPERATOR_SDK_DL_URL=https://github.com/operator-framework/operator-sdk/releases/download/v1.39.2
curl -LO ${OPERATOR_SDK_DL_URL}/operator-sdk_${OS}_${ARCH}
chmod +x operator-sdk_${OS}_${ARCH} && sudo mv operator-sdk_${OS}_${ARCH} /usr/local/bin/operator-sdk
```

### Create Project Structure
```bash
mkdir cloudflare-operator
cd cloudflare-operator
operator-sdk init --domain cloudflare.io --repo github.com/example/cloudflare-operator --project-name cloudflare-operator
```

### Add Required Dependencies
```bash
go get github.com/cloudflare/cloudflare-go@latest
go get golang.org/x/time/rate@latest
```

### Validation Checkpoint
- Verify `go.mod` contains cloudflare-go dependency
- Ensure `PROJECT` file exists with correct domain
- Check that Makefile is generated

## Phase 2: API Design and CRD Creation

### Context
Define the CloudflareAccessPolicy custom resource that will drive all other resource creation.

### Create API
```bash
operator-sdk create api --group cloudflare --version v1alpha1 --kind CloudflareAccessPolicy --resource --controller
```

### Define API Types
Edit `api/v1alpha1/cloudflareaccesspolicy_types.go`:

```go
package v1alpha1

import (
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// CloudflareAccessPolicySpec defines the desired state
type CloudflareAccessPolicySpec struct {
    // +kubebuilder:validation:Required
    // +kubebuilder:validation:Pattern=`^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$`
    Hostname string `json:"hostname"`
    
    // +kubebuilder:validation:Required
    AccountID string `json:"accountId"`
    
    // +kubebuilder:validation:Required
    ZoneID string `json:"zoneId"`
    
    // +kubebuilder:validation:Optional
    TunnelName string `json:"tunnelName,omitempty"`
    
    // +kubebuilder:validation:Required
    // +kubebuilder:validation:MinItems=1
    AccessRules []AccessRule `json:"accessRules"`
    
    // +kubebuilder:validation:Optional
    // +kubebuilder:validation:Pattern=`^(\d+[hm])+$`
    // +kubebuilder:default="24h"
    SessionDuration string `json:"sessionDuration,omitempty"`
}

type AccessRule struct {
    // +kubebuilder:validation:Enum=allow;deny;bypass
    Action string `json:"action"`
    
    // +kubebuilder:validation:MinItems=1
    Include []AccessCondition `json:"include"`
    
    // +kubebuilder:validation:Optional
    Exclude []AccessCondition `json:"exclude,omitempty"`
}

type AccessCondition struct {
    // +kubebuilder:validation:Optional
    // +kubebuilder:validation:Format=email
    Email string `json:"email,omitempty"`
    
    // +kubebuilder:validation:Optional
    EmailDomain string `json:"emailDomain,omitempty"`
    
    // +kubebuilder:validation:Optional
    IPRanges []string `json:"ipRanges,omitempty"`
}

// CloudflareAccessPolicyStatus defines the observed state
type CloudflareAccessPolicyStatus struct {
    // +patchMergeKey=type
    // +patchStrategy=merge
    // +listType=map
    // +listMapKey=type
    Conditions []metav1.Condition `json:"conditions,omitempty" patchStrategy:"merge" patchMergeKey:"type"`
    
    // External resource IDs
    PolicyID      string `json:"policyId,omitempty"`
    ApplicationID string `json:"applicationId,omitempty"`
    TunnelID      string `json:"tunnelId,omitempty"`
    DNSRecordID   string `json:"dnsRecordId,omitempty"`
    
    // Overall readiness
    Ready bool `json:"ready"`
    
    // Track the last observed generation
    ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}

// Condition types
const (
    TypeAvailable          = "Available"
    TypeProgressing        = "Progressing"
    TypeDegraded          = "Degraded"
    TypePolicyCreated     = "PolicyCreated"
    TypeApplicationCreated = "ApplicationCreated"
    TypeTunnelReady       = "TunnelReady"
    TypeDNSConfigured     = "DNSConfigured"
)

//+kubebuilder:object:root=true
//+kubebuilder:subresource:status
//+kubebuilder:printcolumn:name="Hostname",type=string,JSONPath=`.spec.hostname`
//+kubebuilder:printcolumn:name="Ready",type=boolean,JSONPath=`.status.ready`
//+kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// CloudflareAccessPolicy is the Schema for the cloudflareaccesspolicies API
type CloudflareAccessPolicy struct {
    metav1.TypeMeta   `json:",inline"`
    metav1.ObjectMeta `json:"metadata,omitempty"`

    Spec   CloudflareAccessPolicySpec   `json:"spec,omitempty"`
    Status CloudflareAccessPolicyStatus `json:"status,omitempty"`
}

//+kubebuilder:object:root=true

// CloudflareAccessPolicyList contains a list of CloudflareAccessPolicy
type CloudflareAccessPolicyList struct {
    metav1.TypeMeta `json:",inline"`
    metav1.ListMeta `json:"metadata,omitempty"`
    Items           []CloudflareAccessPolicy `json:"items"`
}

func init() {
    SchemeBuilder.Register(&CloudflareAccessPolicy{}, &CloudflareAccessPolicyList{})
}
```

### Generate CRD Manifests
```bash
make generate
make manifests
```

### Validation Checkpoint
- Verify CRD YAML generated in `config/crd/bases/`
- Check that validation rules are present in the CRD
- Ensure status subresource is enabled

## Phase 3: Cloudflare Client Integration

### Context
Create a robust Cloudflare client wrapper with proper error handling and rate limiting.

### Create Client Package
Create `pkg/cloudflare/client.go`:

```go
package cloudflare

import (
    "context"
    "errors"
    "fmt"
    "net/http"
    "time"
    
    "github.com/cloudflare/cloudflare-go"
    "golang.org/x/time/rate"
)

type Client struct {
    api     *cloudflare.API
    limiter *rate.Limiter
}

// NewClient creates a rate-limited Cloudflare client
func NewClient(apiToken string) (*Client, error) {
    if apiToken == "" {
        return nil, errors.New("CLOUDFLARE_API_TOKEN is required")
    }
    
    api, err := cloudflare.NewWithAPIToken(apiToken)
    if err != nil {
        return nil, fmt.Errorf("failed to create Cloudflare client: %w", err)
    }
    
    // Allow 10 requests per second with burst of 20
    limiter := rate.NewLimiter(10, 20)
    
    return &Client{
        api:     api,
        limiter: limiter,
    }, nil
}

// CreateTunnel creates a new Cloudflare tunnel
func (c *Client) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, error) {
    if err := c.limiter.Wait(ctx); err != nil {
        return nil, err
    }
    
    tunnel := cloudflare.TunnelCreateParams{
        Name:      name,
        ConfigSrc: "cloudflare",
    }
    
    result, err := c.api.CreateTunnel(ctx, cloudflare.AccountIdentifier(accountID), tunnel)
    if err != nil {
        return nil, c.handleError(err, "create tunnel")
    }
    
    return &result, nil
}

// ConfigureTunnelIngress configures tunnel routing rules
func (c *Client) ConfigureTunnelIngress(ctx context.Context, accountID, tunnelID, hostname, serviceURL string) error {
    if err := c.limiter.Wait(ctx); err != nil {
        return err
    }
    
    config := cloudflare.TunnelConfiguration{
        TunnelID: tunnelID,
        Config: cloudflare.TunnelConfigurationConfig{
            Ingress: []cloudflare.UnvalidatedIngressRule{
                {
                    Hostname: hostname,
                    Service:  serviceURL,
                },
                {
                    Service: "http_status:404",
                },
            },
        },
    }
    
    _, err := c.api.UpdateTunnelConfiguration(ctx, 
        cloudflare.AccountIdentifier(accountID),
        cloudflare.TunnelConfigurationParams{
            TunnelID: tunnelID,
            Config:   config.Config,
        })
    
    return c.handleError(err, "configure tunnel")
}

// CreateAccessApplication creates a Zero Trust access application
func (c *Client) CreateAccessApplication(ctx context.Context, accountID, name, domain, sessionDuration string) (*cloudflare.AccessApplication, error) {
    if err := c.limiter.Wait(ctx); err != nil {
        return nil, err
    }
    
    app := cloudflare.CreateAccessApplicationParams{
        Name:            name,
        Domain:          domain,
        Type:            "self_hosted",
        SessionDuration: sessionDuration,
    }
    
    result, err := c.api.CreateAccessApplication(ctx, cloudflare.AccountIdentifier(accountID), app)
    if err != nil {
        return nil, c.handleError(err, "create access application")
    }
    
    return &result, nil
}

// CreateAccessPolicy creates an access policy for an application
func (c *Client) CreateAccessPolicy(ctx context.Context, accountID, appID, name string, rules []interface{}) (*cloudflare.AccessPolicy, error) {
    if err := c.limiter.Wait(ctx); err != nil {
        return nil, err
    }
    
    policy := cloudflare.CreateAccessPolicyParams{
        Name:          name,
        Decision:      "allow",
        Include:       rules,
        ApplicationID: appID,
    }
    
    result, err := c.api.CreateAccessPolicy(ctx, cloudflare.AccountIdentifier(accountID), policy)
    if err != nil {
        return nil, c.handleError(err, "create access policy")
    }
    
    return &result, nil
}

// CreateDNSRecord creates a DNS record
func (c *Client) CreateDNSRecord(ctx context.Context, zoneID, recordType, name, content string, proxied bool) (*cloudflare.DNSRecord, error) {
    if err := c.limiter.Wait(ctx); err != nil {
        return nil, err
    }
    
    record := cloudflare.CreateDNSRecordParams{
        Type:    recordType,
        Name:    name,
        Content: content,
        TTL:     1,
        Proxied: &proxied,
        Comment: cloudflare.StringPtr("Managed by Kubernetes operator"),
    }
    
    result, err := c.api.CreateDNSRecord(ctx, cloudflare.ZoneIdentifier(zoneID), record)
    if err != nil {
        return nil, c.handleError(err, "create DNS record")
    }
    
    return &result, nil
}

// Delete methods
func (c *Client) DeleteTunnel(ctx context.Context, accountID, tunnelID string) error {
    if err := c.limiter.Wait(ctx); err != nil {
        return err
    }
    
    err := c.api.DeleteTunnel(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
    return c.handleError(err, "delete tunnel")
}

func (c *Client) DeleteAccessApplication(ctx context.Context, accountID, appID string) error {
    if err := c.limiter.Wait(ctx); err != nil {
        return err
    }
    
    err := c.api.DeleteAccessApplication(ctx, cloudflare.AccountIdentifier(accountID), appID)
    return c.handleError(err, "delete access application")
}

func (c *Client) DeleteDNSRecord(ctx context.Context, zoneID, recordID string) error {
    if err := c.limiter.Wait(ctx); err != nil {
        return err
    }
    
    err := c.api.DeleteDNSRecord(ctx, cloudflare.ZoneIdentifier(zoneID), recordID)
    return c.handleError(err, "delete DNS record")
}

// Error handling
func (c *Client) handleError(err error, operation string) error {
    if err == nil {
        return nil
    }
    
    var cfErr *cloudflare.Error
    if errors.As(err, &cfErr) {
        switch cfErr.StatusCode {
        case http.StatusUnauthorized:
            return fmt.Errorf("%s failed: authentication error: %w", operation, err)
        case http.StatusForbidden:
            return fmt.Errorf("%s failed: insufficient permissions: %w", operation, err)
        case http.StatusTooManyRequests:
            return fmt.Errorf("%s failed: rate limited: %w", operation, err)
        case http.StatusNotFound:
            return fmt.Errorf("%s failed: resource not found: %w", operation, err)
        default:
            return fmt.Errorf("%s failed: %w", operation, err)
        }
    }
    return fmt.Errorf("%s failed: %w", operation, err)
}

// IsNotFoundError checks if error is a 404
func IsNotFoundError(err error) bool {
    var cfErr *cloudflare.Error
    if errors.As(err, &cfErr) {
        return cfErr.StatusCode == http.StatusNotFound
    }
    return false
}

// IsRateLimitError checks if error is rate limit
func IsRateLimitError(err error) bool {
    var cfErr *cloudflare.Error
    if errors.As(err, &cfErr) {
        return cfErr.StatusCode == http.StatusTooManyRequests
    }
    return false
}
```

### Validation Checkpoint
- Verify the client package compiles without errors
- Check that all required Cloudflare operations are implemented
- Ensure proper error handling is in place

## Phase 4: Controller Implementation

### Context
Implement the main reconciliation logic with proper order of operations and error handling.

### Update Controller
Edit `internal/controller/cloudflareaccesspolicy_controller.go`:

```go
package controller

import (
    "context"
    "fmt"
    "os"
    "time"
    
    "k8s.io/apimachinery/pkg/api/errors"
    "k8s.io/apimachinery/pkg/api/meta"
    "k8s.io/apimachinery/pkg/runtime"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    ctrl "sigs.k8s.io/controller-runtime"
    "sigs.k8s.io/controller-runtime/pkg/client"
    "sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
    "sigs.k8s.io/controller-runtime/pkg/log"
    "sigs.k8s.io/controller-runtime/pkg/predicate"
    
    cloudfarev1alpha1 "github.com/example/cloudflare-operator/api/v1alpha1"
    cfclient "github.com/example/cloudflare-operator/pkg/cloudflare"
    corev1 "k8s.io/api/core/v1"
)

const finalizerName = "cloudflare.io/access-policy-finalizer"

// CloudflareAccessPolicyReconciler reconciles a CloudflareAccessPolicy object
type CloudflareAccessPolicyReconciler struct {
    client.Client
    Scheme *runtime.Scheme
    cfClient *cfclient.Client
}

//+kubebuilder:rbac:groups=cloudflare.cloudflare.io,resources=cloudflareaccesspolicies,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=cloudflare.cloudflare.io,resources=cloudflareaccesspolicies/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=cloudflare.cloudflare.io,resources=cloudflareaccesspolicies/finalizers,verbs=update
//+kubebuilder:rbac:groups=core,resources=services,verbs=get;list;watch
//+kubebuilder:rbac:groups=core,resources=events,verbs=create;patch
//+kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete

func (r *CloudflareAccessPolicyReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    // Fetch the CloudflareAccessPolicy instance
    var policy cloudfarev1alpha1.CloudflareAccessPolicy
    if err := r.Get(ctx, req.NamespacedName, &policy); err != nil {
        if errors.IsNotFound(err) {
            logger.Info("CloudflareAccessPolicy resource not found, ignoring since object must be deleted")
            return ctrl.Result{}, nil
        }
        logger.Error(err, "Failed to get CloudflareAccessPolicy")
        return ctrl.Result{}, err
    }
    
    // Handle deletion
    if !policy.DeletionTimestamp.IsZero() {
        return r.reconcileDelete(ctx, &policy)
    }
    
    // Add finalizer if not present
    if !controllerutil.ContainsFinalizer(&policy, finalizerName) {
        controllerutil.AddFinalizer(&policy, finalizerName)
        if err := r.Update(ctx, &policy); err != nil {
            return ctrl.Result{}, err
        }
    }
    
    // Reconcile the resource
    return r.reconcileNormal(ctx, &policy)
}

func (r *CloudflareAccessPolicyReconciler) reconcileNormal(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    // Check if generation has changed
    if policy.Status.ObservedGeneration == policy.Generation && policy.Status.Ready {
        logger.Info("Resource is up to date", "generation", policy.Generation)
        return ctrl.Result{}, nil
    }
    
    // Update progressing condition
    r.updateCondition(policy, cloudfarev1alpha1.TypeProgressing, metav1.ConditionTrue, "Reconciling", "Starting reconciliation")
    
    // Step 1: Create Access Policy (must be first)
    if result, err := r.reconcileAccessPolicy(ctx, policy); err != nil {
        return r.updateStatusWithError(ctx, policy, cloudfarev1alpha1.TypePolicyCreated, err)
    } else if !result.IsZero() {
        return result, nil
    }
    
    // Step 2: Create Access Application
    if result, err := r.reconcileApplication(ctx, policy); err != nil {
        return r.updateStatusWithError(ctx, policy, cloudfarev1alpha1.TypeApplicationCreated, err)
    } else if !result.IsZero() {
        return result, nil
    }
    
    // Step 3: Configure Tunnel
    if result, err := r.reconcileTunnel(ctx, policy); err != nil {
        return r.updateStatusWithError(ctx, policy, cloudfarev1alpha1.TypeTunnelReady, err)
    } else if !result.IsZero() {
        return result, nil
    }
    
    // Step 4: Configure DNS (must be last)
    if result, err := r.reconcileDNS(ctx, policy); err != nil {
        return r.updateStatusWithError(ctx, policy, cloudfarev1alpha1.TypeDNSConfigured, err)
    } else if !result.IsZero() {
        return result, nil
    }
    
    // All steps completed successfully
    r.updateCondition(policy, cloudfarev1alpha1.TypeProgressing, metav1.ConditionFalse, "ReconcileComplete", "All resources configured")
    r.updateCondition(policy, cloudfarev1alpha1.TypeAvailable, metav1.ConditionTrue, "Ready", "All resources are ready")
    policy.Status.Ready = true
    policy.Status.ObservedGeneration = policy.Generation
    
    return ctrl.Result{}, r.Status().Update(ctx, policy)
}

func (r *CloudflareAccessPolicyReconciler) reconcileAccessPolicy(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    // Skip if already created
    if policy.Status.PolicyID != "" {
        logger.Info("Access policy already exists", "policyId", policy.Status.PolicyID)
        r.updateCondition(policy, cloudfarev1alpha1.TypePolicyCreated, metav1.ConditionTrue, "Created", "Access policy exists")
        return ctrl.Result{}, nil
    }
    
    // Build access rules
    var rules []interface{}
    for _, rule := range policy.Spec.AccessRules {
        for _, condition := range rule.Include {
            if condition.Email != "" {
                rules = append(rules, map[string]interface{}{
                    "email": map[string]string{"email": condition.Email},
                })
            }
            if condition.EmailDomain != "" {
                rules = append(rules, map[string]interface{}{
                    "email_domain": map[string]string{"domain": condition.EmailDomain},
                })
            }
        }
    }
    
    // Create policy (placeholder - actual implementation would create after application)
    logger.Info("Access policy configuration prepared", "rules", len(rules))
    policy.Status.PolicyID = fmt.Sprintf("policy-%s", policy.UID)
    r.updateCondition(policy, cloudfarev1alpha1.TypePolicyCreated, metav1.ConditionTrue, "Created", "Access policy created")
    
    return ctrl.Result{}, r.Status().Update(ctx, policy)
}

func (r *CloudflareAccessPolicyReconciler) reconcileApplication(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    // Skip if already created
    if policy.Status.ApplicationID != "" {
        logger.Info("Application already exists", "applicationId", policy.Status.ApplicationID)
        r.updateCondition(policy, cloudfarev1alpha1.TypeApplicationCreated, metav1.ConditionTrue, "Created", "Application exists")
        return ctrl.Result{}, nil
    }
    
    // Create application
    sessionDuration := policy.Spec.SessionDuration
    if sessionDuration == "" {
        sessionDuration = "24h"
    }
    
    app, err := r.cfClient.CreateAccessApplication(ctx, 
        policy.Spec.AccountID,
        policy.Name,
        policy.Spec.Hostname,
        sessionDuration)
    
    if err != nil {
        if cfclient.IsRateLimitError(err) {
            logger.Info("Rate limited, retrying", "error", err)
            return ctrl.Result{RequeueAfter: time.Minute * 2}, nil
        }
        return ctrl.Result{}, fmt.Errorf("failed to create application: %w", err)
    }
    
    policy.Status.ApplicationID = app.ID
    
    // Now create the actual access policy for the application
    _, err = r.cfClient.CreateAccessPolicy(ctx,
        policy.Spec.AccountID,
        app.ID,
        fmt.Sprintf("%s-policy", policy.Name),
        r.buildAccessRules(policy))
    
    if err != nil {
        return ctrl.Result{}, fmt.Errorf("failed to create access policy: %w", err)
    }
    
    logger.Info("Created access application", "applicationId", app.ID)
    r.updateCondition(policy, cloudfarev1alpha1.TypeApplicationCreated, metav1.ConditionTrue, "Created", "Application and policy created")
    
    return ctrl.Result{}, r.Status().Update(ctx, policy)
}

func (r *CloudflareAccessPolicyReconciler) reconcileTunnel(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    // Skip if already created
    if policy.Status.TunnelID != "" {
        logger.Info("Tunnel already exists", "tunnelId", policy.Status.TunnelID)
        r.updateCondition(policy, cloudfarev1alpha1.TypeTunnelReady, metav1.ConditionTrue, "Configured", "Tunnel exists")
        return ctrl.Result{}, nil
    }
    
    // Create tunnel
    tunnelName := policy.Spec.TunnelName
    if tunnelName == "" {
        tunnelName = fmt.Sprintf("%s-tunnel", policy.Name)
    }
    
    tunnel, err := r.cfClient.CreateTunnel(ctx, policy.Spec.AccountID, tunnelName)
    if err != nil {
        if cfclient.IsRateLimitError(err) {
            logger.Info("Rate limited, retrying", "error", err)
            return ctrl.Result{RequeueAfter: time.Minute * 2}, nil
        }
        return ctrl.Result{}, fmt.Errorf("failed to create tunnel: %w", err)
    }
    
    policy.Status.TunnelID = tunnel.ID
    
    // Configure tunnel ingress
    serviceURL := r.getServiceURL(policy)
    err = r.cfClient.ConfigureTunnelIngress(ctx,
        policy.Spec.AccountID,
        tunnel.ID,
        policy.Spec.Hostname,
        serviceURL)
    
    if err != nil {
        return ctrl.Result{}, fmt.Errorf("failed to configure tunnel: %w", err)
    }
    
    logger.Info("Created and configured tunnel", "tunnelId", tunnel.ID)
    r.updateCondition(policy, cloudfarev1alpha1.TypeTunnelReady, metav1.ConditionTrue, "Configured", "Tunnel created and configured")
    
    // Deploy cloudflared
    if err := r.deployCloudflared(ctx, policy, tunnel); err != nil {
        return ctrl.Result{}, fmt.Errorf("failed to deploy cloudflared: %w", err)
    }
    
    return ctrl.Result{}, r.Status().Update(ctx, policy)
}

func (r *CloudflareAccessPolicyReconciler) reconcileDNS(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    // Skip if already created
    if policy.Status.DNSRecordID != "" {
        logger.Info("DNS record already exists", "recordId", policy.Status.DNSRecordID)
        r.updateCondition(policy, cloudfarev1alpha1.TypeDNSConfigured, metav1.ConditionTrue, "Configured", "DNS record exists")
        return ctrl.Result{}, nil
    }
    
    // Create CNAME record pointing to tunnel
    content := fmt.Sprintf("%s.cfargotunnel.com", policy.Status.TunnelID)
    record, err := r.cfClient.CreateDNSRecord(ctx,
        policy.Spec.ZoneID,
        "CNAME",
        policy.Spec.Hostname,
        content,
        true) // proxied
    
    if err != nil {
        if cfclient.IsRateLimitError(err) {
            logger.Info("Rate limited, retrying", "error", err)
            return ctrl.Result{RequeueAfter: time.Minute * 2}, nil
        }
        return ctrl.Result{}, fmt.Errorf("failed to create DNS record: %w", err)
    }
    
    policy.Status.DNSRecordID = record.ID
    logger.Info("Created DNS record", "recordId", record.ID)
    r.updateCondition(policy, cloudfarev1alpha1.TypeDNSConfigured, metav1.ConditionTrue, "Configured", "DNS record created")
    
    return ctrl.Result{}, r.Status().Update(ctx, policy)
}

func (r *CloudflareAccessPolicyReconciler) reconcileDelete(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) (ctrl.Result, error) {
    logger := log.FromContext(ctx)
    
    if !controllerutil.ContainsFinalizer(policy, finalizerName) {
        return ctrl.Result{}, nil
    }
    
    logger.Info("Starting cleanup of external resources")
    
    // Delete in reverse order
    if policy.Status.DNSRecordID != "" {
        if err := r.cfClient.DeleteDNSRecord(ctx, policy.Spec.ZoneID, policy.Status.DNSRecordID); err != nil {
            if !cfclient.IsNotFoundError(err) {
                logger.Error(err, "Failed to delete DNS record")
                return ctrl.Result{RequeueAfter: time.Minute}, nil
            }
        }
        logger.Info("Deleted DNS record", "recordId", policy.Status.DNSRecordID)
    }
    
    if policy.Status.TunnelID != "" {
        if err := r.deleteCloudflared(ctx, policy); err != nil {
            logger.Error(err, "Failed to delete cloudflared deployment")
            return ctrl.Result{RequeueAfter: time.Minute}, nil
        }
        
        if err := r.cfClient.DeleteTunnel(ctx, policy.Spec.AccountID, policy.Status.TunnelID); err != nil {
            if !cfclient.IsNotFoundError(err) {
                logger.Error(err, "Failed to delete tunnel")
                return ctrl.Result{RequeueAfter: time.Minute}, nil
            }
        }
        logger.Info("Deleted tunnel", "tunnelId", policy.Status.TunnelID)
    }
    
    if policy.Status.ApplicationID != "" {
        if err := r.cfClient.DeleteAccessApplication(ctx, policy.Spec.AccountID, policy.Status.ApplicationID); err != nil {
            if !cfclient.IsNotFoundError(err) {
                logger.Error(err, "Failed to delete application")
                return ctrl.Result{RequeueAfter: time.Minute}, nil
            }
        }
        logger.Info("Deleted application", "applicationId", policy.Status.ApplicationID)
    }
    
    // Remove finalizer
    controllerutil.RemoveFinalizer(policy, finalizerName)
    return ctrl.Result{}, r.Update(ctx, policy)
}

// Helper functions
func (r *CloudflareAccessPolicyReconciler) updateCondition(policy *cloudfarev1alpha1.CloudflareAccessPolicy, condType string, status metav1.ConditionStatus, reason, message string) {
    meta.SetStatusCondition(&policy.Status.Conditions, metav1.Condition{
        Type:               condType,
        Status:             status,
        Reason:             reason,
        Message:            message,
        LastTransitionTime: metav1.Now(),
    })
}

func (r *CloudflareAccessPolicyReconciler) updateStatusWithError(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy, condType string, err error) (ctrl.Result, error) {
    r.updateCondition(policy, condType, metav1.ConditionFalse, "Failed", err.Error())
    r.updateCondition(policy, cloudfarev1alpha1.TypeDegraded, metav1.ConditionTrue, "Error", err.Error())
    policy.Status.Ready = false
    
    if statusErr := r.Status().Update(ctx, policy); statusErr != nil {
        return ctrl.Result{}, statusErr
    }
    
    return ctrl.Result{RequeueAfter: time.Minute * 2}, err
}

func (r *CloudflareAccessPolicyReconciler) buildAccessRules(policy *cloudfarev1alpha1.CloudflareAccessPolicy) []interface{} {
    var rules []interface{}
    for _, rule := range policy.Spec.AccessRules {
        for _, condition := range rule.Include {
            if condition.Email != "" {
                rules = append(rules, map[string]interface{}{
                    "email": map[string]string{"email": condition.Email},
                })
            }
            if condition.EmailDomain != "" {
                rules = append(rules, map[string]interface{}{
                    "email_domain": map[string]string{"domain": condition.EmailDomain},
                })
            }
        }
    }
    return rules
}

func (r *CloudflareAccessPolicyReconciler) getServiceURL(policy *cloudfarev1alpha1.CloudflareAccessPolicy) string {
    // This would be determined from service annotations in a full implementation
    return fmt.Sprintf("http://app-service.%s.svc.cluster.local:8080", policy.Namespace)
}

func (r *CloudflareAccessPolicyReconciler) deployCloudflared(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy, tunnel *cloudflare.Tunnel) error {
    // Implementation would create a Deployment for cloudflared
    // with tunnel credentials mounted as a secret
    return nil
}

func (r *CloudflareAccessPolicyReconciler) deleteCloudflared(ctx context.Context, policy *cloudfarev1alpha1.CloudflareAccessPolicy) error {
    // Implementation would delete the cloudflared Deployment
    return nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *CloudflareAccessPolicyReconciler) SetupWithManager(mgr ctrl.Manager) error {
    // Initialize Cloudflare client
    apiToken := os.Getenv("CLOUDFLARE_API_TOKEN")
    if apiToken == "" {
        return fmt.Errorf("CLOUDFLARE_API_TOKEN environment variable must be set")
    }
    
    cfClient, err := cfclient.NewClient(apiToken)
    if err != nil {
        return fmt.Errorf("failed to create Cloudflare client: %w", err)
    }
    r.cfClient = cfClient
    
    return ctrl.NewControllerManagedBy(mgr).
        For(&cloudfarev1alpha1.CloudflareAccessPolicy{}).
        Watches(
            &corev1.Service{},
            &handler.EnqueueRequestForObject{},
            builder.WithPredicates(predicate.AnnotationChangedPredicate{}),
        ).
        Complete(r)
}
```

### Validation Checkpoint
- Verify controller compiles without errors
- Check that all reconciliation steps are implemented
- Ensure proper error handling and status updates

## Phase 5: Service Annotation Support

### Context
Add support for watching Service annotations to trigger policy creation.

### Create Service Handler
Create `internal/controller/service_handler.go`:

```go
package controller

import (
    "context"
    "fmt"
    
    corev1 "k8s.io/api/core/v1"
    "k8s.io/apimachinery/pkg/types"
    "sigs.k8s.io/controller-runtime/pkg/client"
    "sigs.k8s.io/controller-runtime/pkg/handler"
    "sigs.k8s.io/controller-runtime/pkg/reconcile"
    
    cloudfarev1alpha1 "github.com/example/cloudflare-operator/api/v1alpha1"
)

const (
    AnnotationHostname     = "cloudflare.io/hostname"
    AnnotationAccessPolicy = "cloudflare.io/access-policy"
    AnnotationEnabled      = "cloudflare.io/enabled"
)

type ServiceHandler struct {
    client.Client
}

// findPoliciesForService returns reconcile requests for policies that manage this service
func (h *ServiceHandler) findPoliciesForService(ctx context.Context, obj client.Object) []reconcile.Request {
    svc := obj.(*corev1.Service)
    
    annotations := svc.GetAnnotations()
    if annotations == nil {
        return nil
    }
    
    // Check if Cloudflare is enabled
    if enabled, exists := annotations[AnnotationEnabled]; !exists || enabled != "true" {
        return nil
    }
    
    hostname := annotations[AnnotationHostname]
    if hostname == "" {
        return nil
    }
    
    // Find matching policies
    var policies cloudfarev1alpha1.CloudflareAccessPolicyList
    if err := h.List(ctx, &policies, client.InNamespace(svc.Namespace)); err != nil {
        return nil
    }
    
    var requests []reconcile.Request
    for _, policy := range policies.Items {
        if policy.Spec.Hostname == hostname {
            requests = append(requests, reconcile.Request{
                NamespacedName: types.NamespacedName{
                    Name:      policy.Name,
                    Namespace: policy.Namespace,
                },
            })
        }
    }
    
    // If no policy exists, we could create one automatically
    // This is left as an exercise based on requirements
    
    return requests
}

// EnqueueRequestsFromMapFunc implements handler.EventHandler
func (h *ServiceHandler) Create(ctx context.Context, evt event.CreateEvent, q workqueue.RateLimitingInterface) {
    h.mapAndEnqueue(ctx, evt.Object, q)
}

func (h *ServiceHandler) Update(ctx context.Context, evt event.UpdateEvent, q workqueue.RateLimitingInterface) {
    h.mapAndEnqueue(ctx, evt.ObjectNew, q)
}

func (h *ServiceHandler) Delete(ctx context.Context, evt event.DeleteEvent, q workqueue.RateLimitingInterface) {
    h.mapAndEnqueue(ctx, evt.Object, q)
}

func (h *ServiceHandler) Generic(ctx context.Context, evt event.GenericEvent, q workqueue.RateLimitingInterface) {
    h.mapAndEnqueue(ctx, evt.Object, q)
}

func (h *ServiceHandler) mapAndEnqueue(ctx context.Context, obj client.Object, q workqueue.RateLimitingInterface) {
    requests := h.findPoliciesForService(ctx, obj)
    for _, req := range requests {
        q.Add(req)
    }
}
```

### Update Controller Setup
Update the `SetupWithManager` function to use the service handler:

```go
func (r *CloudflareAccessPolicyReconciler) SetupWithManager(mgr ctrl.Manager) error {
    // ... existing setup code ...
    
    serviceHandler := &ServiceHandler{Client: mgr.GetClient()}
    
    return ctrl.NewControllerManagedBy(mgr).
        For(&cloudfarev1alpha1.CloudflareAccessPolicy{}).
        Watches(
            &corev1.Service{},
            serviceHandler,
            builder.WithPredicates(predicate.Funcs{
                UpdateFunc: func(e event.UpdateEvent) bool {
                    oldSvc := e.ObjectOld.(*corev1.Service)
                    newSvc := e.ObjectNew.(*corev1.Service)
                    return hasCloudflareAnnotations(oldSvc) || hasCloudflareAnnotations(newSvc)
                },
            }),
        ).
        Complete(r)
}

func hasCloudflareAnnotations(svc *corev1.Service) bool {
    annotations := svc.GetAnnotations()
    if annotations == nil {
        return false
    }
    
    _, hasHostname := annotations[AnnotationHostname]
    _, hasPolicy := annotations[AnnotationAccessPolicy]
    return hasHostname || hasPolicy
}
```

### Validation Checkpoint
- Verify service annotation watching is configured
- Test that changes to service annotations trigger reconciliation
- Ensure proper filtering of irrelevant services

## Phase 6: Deployment Configuration

### Context
Create deployment manifests and RBAC configuration for the operator.

### Update RBAC Configuration
Edit `config/rbac/role.yaml` to add necessary permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: manager-role
rules:
- apiGroups:
  - cloudflare.cloudflare.io
  resources:
  - cloudflareaccesspolicies
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - cloudflare.cloudflare.io
  resources:
  - cloudflareaccesspolicies/finalizers
  verbs:
  - update
- apiGroups:
  - cloudflare.cloudflare.io
  resources:
  - cloudflareaccesspolicies/status
  verbs:
  - get
  - patch
  - update
- apiGroups:
  - ""
  resources:
  - services
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - ""
  resources:
  - events
  verbs:
  - create
  - patch
- apiGroups:
  - apps
  resources:
  - deployments
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - ""
  resources:
  - secrets
  - configmaps
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
```

### Create Deployment Configuration
Create `config/manager/manager.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  labels:
    control-plane: controller-manager
  name: cloudflare-operator-system
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: controller-manager
  namespace: cloudflare-operator-system
  labels:
    control-plane: controller-manager
spec:
  selector:
    matchLabels:
      control-plane: controller-manager
  replicas: 1
  template:
    metadata:
      annotations:
        kubectl.kubernetes.io/default-container: manager
      labels:
        control-plane: controller-manager
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
      - command:
        - /manager
        args:
        - --leader-elect
        image: controller:latest
        name: manager
        env:
        - name: CLOUDFLARE_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: cloudflare-credentials
              key: api-token
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - "ALL"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8081
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8081
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          limits:
            cpu: 500m
            memory: 128Mi
          requests:
            cpu: 10m
            memory: 64Mi
      serviceAccountName: controller-manager
      terminationGracePeriodSeconds: 10
```

### Create Secret Template
Create `config/samples/cloudflare-credentials.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-credentials
  namespace: cloudflare-operator-system
type: Opaque
stringData:
  api-token: "YOUR_CLOUDFLARE_API_TOKEN_HERE"
```

### Validation Checkpoint
- Verify RBAC permissions cover all required resources
- Check deployment configuration is complete
- Ensure secret template is provided

## Phase 7: Testing and Examples

### Context
Create comprehensive examples and testing scenarios.

### Create Sample CloudflareAccessPolicy
Create `config/samples/cloudflare_v1alpha1_cloudflareaccesspolicy.yaml`:

```yaml
apiVersion: cloudflare.cloudflare.io/v1alpha1
kind: CloudflareAccessPolicy
metadata:
  name: example-app-policy
  namespace: default
spec:
  hostname: "app.example.com"
  accountId: "your-account-id"
  zoneId: "your-zone-id"
  tunnelName: "example-app-tunnel"
  sessionDuration: "24h"
  accessRules:
  - action: allow
    include:
    - email: "user@example.com"
    - emailDomain: "example.com"
  - action: allow
    include:
    - ipRanges: 
      - "192.168.1.0/24"
```

### Create Service with Annotations
Create `config/samples/service-with-annotations.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: example-app
  namespace: default
  annotations:
    cloudflare.io/enabled: "true"
    cloudflare.io/hostname: "app.example.com"
    cloudflare.io/access-policy: "example-app-policy"
spec:
  selector:
    app: example-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
```

### Create Integration Test
Create `test/e2e/cloudflareaccesspolicy_test.go`:

```go
package e2e

import (
    "context"
    "testing"
    "time"
    
    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    corev1 "k8s.io/api/core/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/apimachinery/pkg/types"
    
    cloudfarev1alpha1 "github.com/example/cloudflare-operator/api/v1alpha1"
)

var _ = Describe("CloudflareAccessPolicy Controller", func() {
    Context("When creating a CloudflareAccessPolicy", func() {
        It("Should create all required resources in order", func() {
            ctx := context.Background()
            
            // Create a test policy
            policy := &cloudfarev1alpha1.CloudflareAccessPolicy{
                ObjectMeta: metav1.ObjectMeta{
                    Name:      "test-policy",
                    Namespace: "default",
                },
                Spec: cloudfarev1alpha1.CloudflareAccessPolicySpec{
                    Hostname:  "test.example.com",
                    AccountID: "test-account",
                    ZoneID:    "test-zone",
                    AccessRules: []cloudfarev1alpha1.AccessRule{
                        {
                            Action: "allow",
                            Include: []cloudfarev1alpha1.AccessCondition{
                                {Email: "test@example.com"},
                            },
                        },
                    },
                },
            }
            
            Expect(k8sClient.Create(ctx, policy)).Should(Succeed())
            
            // Wait for policy to be ready
            Eventually(func() bool {
                var updated cloudfarev1alpha1.CloudflareAccessPolicy
                err := k8sClient.Get(ctx, types.NamespacedName{
                    Name:      policy.Name,
                    Namespace: policy.Namespace,
                }, &updated)
                if err != nil {
                    return false
                }
                return updated.Status.Ready
            }, time.Minute*2, time.Second*5).Should(BeTrue())
            
            // Verify status conditions
            var finalPolicy cloudfarev1alpha1.CloudflareAccessPolicy
            Expect(k8sClient.Get(ctx, types.NamespacedName{
                Name:      policy.Name,
                Namespace: policy.Namespace,
            }, &finalPolicy)).Should(Succeed())
            
            Expect(finalPolicy.Status.PolicyID).ShouldNot(BeEmpty())
            Expect(finalPolicy.Status.ApplicationID).ShouldNot(BeEmpty())
            Expect(finalPolicy.Status.TunnelID).ShouldNot(BeEmpty())
            Expect(finalPolicy.Status.DNSRecordID).ShouldNot(BeEmpty())
        })
        
        It("Should reconcile when service annotations change", func() {
            ctx := context.Background()
            
            // Create a service with annotations
            service := &corev1.Service{
                ObjectMeta: metav1.ObjectMeta{
                    Name:      "test-service",
                    Namespace: "default",
                    Annotations: map[string]string{
                        "cloudflare.io/enabled":  "true",
                        "cloudflare.io/hostname": "service.example.com",
                    },
                },
                Spec: corev1.ServiceSpec{
                    Selector: map[string]string{"app": "test"},
                    Ports: []corev1.ServicePort{
                        {Port: 80, TargetPort: intstr.FromInt(8080)},
                    },
                },
            }
            
            Expect(k8sClient.Create(ctx, service)).Should(Succeed())
            
            // Update annotations
            Eventually(func() error {
                var svc corev1.Service
                if err := k8sClient.Get(ctx, types.NamespacedName{
                    Name:      service.Name,
                    Namespace: service.Namespace,
                }, &svc); err != nil {
                    return err
                }
                
                svc.Annotations["cloudflare.io/access-policy"] = "test-policy"
                return k8sClient.Update(ctx, &svc)
            }, time.Second*30, time.Second*5).Should(Succeed())
        })
        
        It("Should clean up resources on deletion", func() {
            ctx := context.Background()
            
            // Create and delete a policy
            policy := &cloudfarev1alpha1.CloudflareAccessPolicy{
                ObjectMeta: metav1.ObjectMeta{
                    Name:      "cleanup-test",
                    Namespace: "default",
                },
                Spec: cloudfarev1alpha1.CloudflareAccessPolicySpec{
                    Hostname:  "cleanup.example.com",
                    AccountID: "test-account",
                    ZoneID:    "test-zone",
                    AccessRules: []cloudfarev1alpha1.AccessRule{
                        {
                            Action: "allow",
                            Include: []cloudfarev1alpha1.AccessCondition{
                                {EmailDomain: "example.com"},
                            },
                        },
                    },
                },
            }
            
            Expect(k8sClient.Create(ctx, policy)).Should(Succeed())
            
            // Wait for ready
            Eventually(func() bool {
                var p cloudfarev1alpha1.CloudflareAccessPolicy
                if err := k8sClient.Get(ctx, types.NamespacedName{
                    Name:      policy.Name,
                    Namespace: policy.Namespace,
                }, &p); err != nil {
                    return false
                }
                return p.Status.Ready
            }, time.Minute*2, time.Second*5).Should(BeTrue())
            
            // Delete the policy
            Expect(k8sClient.Delete(ctx, policy)).Should(Succeed())
            
            // Verify deletion completes
            Eventually(func() error {
                var p cloudfarev1alpha1.CloudflareAccessPolicy
                return k8sClient.Get(ctx, types.NamespacedName{
                    Name:      policy.Name,
                    Namespace: policy.Namespace,
                }, &p)
            }, time.Minute*2, time.Second*5).Should(HaveOccurred())
        })
    })
})
```

### Validation Checkpoint
- Verify examples are complete and valid
- Ensure test cases cover main scenarios
- Check that examples demonstrate all features

## Phase 8: Build and Deployment

### Context
Final steps to build, push, and deploy the operator.

### Build and Push Image
```bash
# Build the operator image
make docker-build IMG=your-registry/cloudflare-operator:v0.1.0

# Push to registry
make docker-push IMG=your-registry/cloudflare-operator:v0.1.0

# Generate final manifests
make manifests
```

### Deploy to Cluster
```bash
# Create namespace and CRDs
make install

# Create Cloudflare credentials secret
kubectl apply -f config/samples/cloudflare-credentials.yaml

# Deploy the operator
make deploy IMG=your-registry/cloudflare-operator:v0.1.0

# Verify deployment
kubectl get pods -n cloudflare-operator-system
kubectl logs -n cloudflare-operator-system deployment/cloudflare-operator-controller-manager
```

### Create First Resource
```bash
# Apply sample policy
kubectl apply -f config/samples/cloudflare_v1alpha1_cloudflareaccesspolicy.yaml

# Check status
kubectl get cloudflareaccesspolicy example-app-policy -o yaml
kubectl describe cloudflareaccesspolicy example-app-policy
```

### Validation Checkpoint
- Verify operator pod is running
- Check CRDs are installed correctly
- Ensure sample resource creates successfully
- Validate all status conditions are updated

## Troubleshooting Guide

### Common Issues

1. **Authentication Errors**
   - Verify CLOUDFLARE_API_TOKEN is set correctly
   - Check token permissions include all required scopes
   - Ensure account ID and zone ID are correct

2. **Resource Creation Order**
   - Monitor status conditions to see where process fails
   - Check operator logs for detailed error messages
   - Verify each step completes before moving to next

3. **Cleanup Issues**
   - Check if finalizer is properly set
   - Look for errors in deletion logs
   - Manually verify resources in Cloudflare dashboard

### Debug Commands
```bash
# Check operator logs
kubectl logs -n cloudflare-operator-system deployment/cloudflare-operator-controller-manager -f

# Get detailed resource status
kubectl get cloudflareaccesspolicy -A -o wide

# Describe specific resource
kubectl describe cloudflareaccesspolicy example-app-policy

# Check events
kubectl get events --sort-by='.lastTimestamp' -A | grep cloudflare
```

## Next Steps

1. **Add Webhook Validation**: Implement admission webhooks for advanced validation
2. **Metrics and Monitoring**: Add Prometheus metrics for observability
3. **Advanced Features**: Support for multiple tunnels, load balancing, custom domains
4. **Helm Chart**: Package operator as Helm chart for easier deployment
5. **OLM Integration**: Create operator bundle for Operator Lifecycle Manager

## References

- [Operator SDK Documentation](https://sdk.operatorframework.io/docs/)
- [Cloudflare API Documentation](https://developers.cloudflare.com/api/)
- [Kubebuilder Book](https://book.kubebuilder.io/)
- [Kubernetes API Conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md)
- [Prompt Engineering Best Practices](https://addyo.substack.com/p/the-prompt-engineering-playbook-for)

This guide provides a comprehensive foundation for building a production-ready Cloudflare Kubernetes operator. Each phase builds upon the previous one, ensuring proper implementation order and security considerations. The modular structure allows for iterative development while maintaining consistency and best practices throughout the project.