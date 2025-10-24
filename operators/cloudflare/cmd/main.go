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

package main

import (
	"context"
	"crypto/tls"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/go-logr/logr"

	// Import all Kubernetes client auth plugins (e.g. Azure, GCP, OIDC, etc.)
	// to ensure that exec-entrypoint and run can make use of them.
	_ "k8s.io/client-go/plugin/pkg/client/auth"

	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/certwatcher"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	"sigs.k8s.io/controller-runtime/pkg/metrics/filters"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"
	"sigs.k8s.io/controller-runtime/pkg/webhook"

	tunnelsv1 "github.com/jomcgi/homelab/operators/cloudflare/api/v1"
	cfclient "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
	"github.com/jomcgi/homelab/operators/cloudflare/internal/controller"
	// +kubebuilder:scaffold:imports
)

var (
	scheme   = runtime.NewScheme()
	setupLog = ctrl.Log.WithName("setup")
)

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))

	utilruntime.Must(tunnelsv1.AddToScheme(scheme))
	// +kubebuilder:scaffold:scheme
}

// nolint:gocyclo
func main() {
	var metricsAddr string
	var metricsCertPath, metricsCertName, metricsCertKey string
	var webhookCertPath, webhookCertName, webhookCertKey string
	var enableLeaderElection bool
	var probeAddr string
	var secureMetrics bool
	var enableHTTP2 bool
	var enableDaemon bool
	var tlsOpts []func(*tls.Config)
	flag.StringVar(&metricsAddr, "metrics-bind-address", "0", "The address the metrics endpoint binds to. "+
		"Use :8443 for HTTPS or :8080 for HTTP, or leave as 0 to disable the metrics service.")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "The address the probe endpoint binds to.")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false,
		"Enable leader election for controller manager. "+
			"Enabling this will ensure there is only one active controller manager.")
	flag.BoolVar(&secureMetrics, "metrics-secure", true,
		"If set, the metrics endpoint is served securely via HTTPS. Use --metrics-secure=false to use HTTP instead.")
	flag.StringVar(&webhookCertPath, "webhook-cert-path", "", "The directory that contains the webhook certificate.")
	flag.StringVar(&webhookCertName, "webhook-cert-name", "tls.crt", "The name of the webhook certificate file.")
	flag.StringVar(&webhookCertKey, "webhook-cert-key", "tls.key", "The name of the webhook key file.")
	flag.StringVar(&metricsCertPath, "metrics-cert-path", "",
		"The directory that contains the metrics server certificate.")
	flag.StringVar(&metricsCertName, "metrics-cert-name", "tls.crt", "The name of the metrics server certificate file.")
	flag.StringVar(&metricsCertKey, "metrics-cert-key", "tls.key", "The name of the metrics server key file.")
	flag.BoolVar(&enableHTTP2, "enable-http2", false,
		"If set, HTTP/2 will be enabled for the metrics and webhook servers")
	flag.BoolVar(&enableDaemon, "enable-daemon", false,
		"If set, automatically create a default tunnel with daemon enabled")
	opts := zap.Options{
		Development: true,
	}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

	// if the enable-http2 flag is false (the default), http/2 should be disabled
	// due to its vulnerabilities. More specifically, disabling http/2 will
	// prevent from being vulnerable to the HTTP/2 Stream Cancellation and
	// Rapid Reset CVEs. For more information see:
	// - https://github.com/advisories/GHSA-qppj-fm5r-hxr3
	// - https://github.com/advisories/GHSA-4374-p667-p6c8
	disableHTTP2 := func(c *tls.Config) {
		setupLog.Info("disabling http/2")
		c.NextProtos = []string{"http/1.1"}
	}

	if !enableHTTP2 {
		tlsOpts = append(tlsOpts, disableHTTP2)
	}

	// Create watchers for metrics and webhooks certificates
	var metricsCertWatcher, webhookCertWatcher *certwatcher.CertWatcher

	// Initial webhook TLS options
	webhookTLSOpts := tlsOpts

	if len(webhookCertPath) > 0 {
		setupLog.Info("Initializing webhook certificate watcher using provided certificates",
			"webhook-cert-path", webhookCertPath, "webhook-cert-name", webhookCertName, "webhook-cert-key", webhookCertKey)

		var err error
		webhookCertWatcher, err = certwatcher.New(
			filepath.Join(webhookCertPath, webhookCertName),
			filepath.Join(webhookCertPath, webhookCertKey),
		)
		if err != nil {
			setupLog.Error(err, "Failed to initialize webhook certificate watcher")
			os.Exit(1)
		}

		webhookTLSOpts = append(webhookTLSOpts, func(config *tls.Config) {
			config.GetCertificate = webhookCertWatcher.GetCertificate
		})
	}

	webhookServer := webhook.NewServer(webhook.Options{
		TLSOpts: webhookTLSOpts,
	})

	// Metrics endpoint is enabled in 'config/default/kustomization.yaml'. The Metrics options configure the server.
	// More info:
	// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.21.0/pkg/metrics/server
	// - https://book.kubebuilder.io/reference/metrics.html
	metricsServerOptions := metricsserver.Options{
		BindAddress:   metricsAddr,
		SecureServing: secureMetrics,
		TLSOpts:       tlsOpts,
	}

	if secureMetrics {
		// FilterProvider is used to protect the metrics endpoint with authn/authz.
		// These configurations ensure that only authorized users and service accounts
		// can access the metrics endpoint. The RBAC are configured in 'config/rbac/kustomization.yaml'. More info:
		// https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.21.0/pkg/metrics/filters#WithAuthenticationAndAuthorization
		metricsServerOptions.FilterProvider = filters.WithAuthenticationAndAuthorization
	}

	// If the certificate is not specified, controller-runtime will automatically
	// generate self-signed certificates for the metrics server. While convenient for development and testing,
	// this setup is not recommended for production.
	//
	// TODO(user): If you enable certManager, uncomment the following lines:
	// - [METRICS-WITH-CERTS] at config/default/kustomization.yaml to generate and use certificates
	// managed by cert-manager for the metrics server.
	// - [PROMETHEUS-WITH-CERTS] at config/prometheus/kustomization.yaml for TLS certification.
	if len(metricsCertPath) > 0 {
		setupLog.Info("Initializing metrics certificate watcher using provided certificates",
			"metrics-cert-path", metricsCertPath, "metrics-cert-name", metricsCertName, "metrics-cert-key", metricsCertKey)

		var err error
		metricsCertWatcher, err = certwatcher.New(
			filepath.Join(metricsCertPath, metricsCertName),
			filepath.Join(metricsCertPath, metricsCertKey),
		)
		if err != nil {
			setupLog.Error(err, "to initialize metrics certificate watcher", "error", err)
			os.Exit(1)
		}

		metricsServerOptions.TLSOpts = append(metricsServerOptions.TLSOpts, func(config *tls.Config) {
			config.GetCertificate = metricsCertWatcher.GetCertificate
		})
	}

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                 scheme,
		Metrics:                metricsServerOptions,
		WebhookServer:          webhookServer,
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "880612ac.tunnels.cloudflare.io",
		// LeaderElectionReleaseOnCancel defines if the leader should step down voluntarily
		// when the Manager ends. This requires the binary to immediately end when the
		// Manager is stopped, otherwise, this setting is unsafe. Setting this significantly
		// speeds up voluntary leader transitions as the new leader don't have to wait
		// LeaseDuration time first.
		//
		// In the default scaffold provided, the program ends immediately after
		// the manager stops, so would be fine to enable this option. However,
		// if you are doing or is intended to do any operation such as perform cleanups
		// after the manager stops then its usage might be unsafe.
		// LeaderElectionReleaseOnCancel: true,
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	// Initialize Cloudflare client
	apiToken := os.Getenv("CLOUDFLARE_API_TOKEN")
	if apiToken == "" {
		setupLog.Error(nil, "CLOUDFLARE_API_TOKEN environment variable is required")
		os.Exit(1)
	}

	cfClient, err := cfclient.NewTunnelClient(apiToken)
	if err != nil {
		setupLog.Error(err, "unable to create Cloudflare client")
		os.Exit(1)
	}

	reconciler := &controller.CloudflareTunnelReconciler{
		Client:   mgr.GetClient(),
		Scheme:   mgr.GetScheme(),
		CFClient: cfClient,
	}
	if err := reconciler.SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "CloudflareTunnel")
		os.Exit(1)
	}

	// Auto-create tunnel if daemon mode is enabled
	if enableDaemon {
		if err := createDefaultTunnel(mgr); err != nil {
			setupLog.Error(err, "unable to create default tunnel")
			os.Exit(1)
		}
	}
	// +kubebuilder:scaffold:builder

	if metricsCertWatcher != nil {
		setupLog.Info("Adding metrics certificate watcher to manager")
		if err := mgr.Add(metricsCertWatcher); err != nil {
			setupLog.Error(err, "unable to add metrics certificate watcher to manager")
			os.Exit(1)
		}
	}

	if webhookCertWatcher != nil {
		setupLog.Info("Adding webhook certificate watcher to manager")
		if err := mgr.Add(webhookCertWatcher); err != nil {
			setupLog.Error(err, "unable to add webhook certificate watcher to manager")
			os.Exit(1)
		}
	}

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	setupLog.Info("starting manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}

func createDefaultTunnel(
	mgr ctrl.Manager,
) error {
	setupLog.Info("daemon mode enabled, will create default tunnel after manager is ready")

	// Validate required environment variables early
	accountID := os.Getenv("CLOUDFLARE_ACCOUNT_ID")
	if accountID == "" {
		return fmt.Errorf("CLOUDFLARE_ACCOUNT_ID environment variable is required for daemon mode")
	}

	operatorNs := os.Getenv("POD_NAMESPACE")
	if operatorNs == "" {
		return fmt.Errorf("POD_NAMESPACE environment variable is required for daemon mode")
	}

	// Start a goroutine to create the tunnel after manager starts
	go func() {
		// Wait for manager to be ready and elected as leader
		<-mgr.Elected()

		// Use background context with timeout for tunnel creation
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()

		log := setupLog.WithValues(
			"namespace", operatorNs,
			"accountID", accountID,
		)

		log.Info("manager ready, checking for existing tunnels")

		// Check if default tunnel already exists
		tunnelList := &tunnelsv1.CloudflareTunnelList{}
		if err := mgr.GetClient().List(ctx, tunnelList); err != nil {
			log.Error(err, "failed to list existing tunnels")
			return
		}

		// Don't create if any tunnel already exists (idempotent)
		if len(tunnelList.Items) > 0 {
			log.Info("tunnel already exists, skipping auto-creation",
				"existingTunnels", len(tunnelList.Items),
			)
			return
		}

		// Use predictable tunnel name for easier identification
		// Format: cloudflare-operator-<namespace>
		tunnelName := fmt.Sprintf("cloudflare-operator-%s", operatorNs)
		crdName := "default-daemon-tunnel"

		log.Info("creating default tunnel CRD",
			"crdName", crdName,
			"tunnelName", tunnelName,
		)

		// Create default tunnel
		defaultTunnel := &tunnelsv1.CloudflareTunnel{
			ObjectMeta: metav1.ObjectMeta{
				Name:      crdName,
				Namespace: operatorNs,
			},
			Spec: tunnelsv1.CloudflareTunnelSpec{
				Name:      tunnelName,
				AccountID: accountID,
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

		// Retry logic with exponential backoff for tunnel creation
		maxRetries := 3
		var createErr error
		for attempt := 0; attempt < maxRetries; attempt++ {
			if attempt > 0 {
				backoff := time.Duration(1<<uint(attempt-1)) * time.Second
				log.Info("retrying tunnel creation after backoff",
					"attempt", attempt+1,
					"maxRetries", maxRetries,
					"backoffSeconds", backoff.Seconds(),
				)
				time.Sleep(backoff)
			}

			createErr = mgr.GetClient().Create(ctx, defaultTunnel)
			if createErr == nil {
				break // Success!
			}

			// Don't retry if it's a conflict error (already exists)
			if errors.IsAlreadyExists(createErr) {
				log.Info("tunnel CRD already exists (created by another replica)",
					"crdName", crdName,
				)
				return
			}

			log.Error(createErr, "failed to create tunnel CRD",
				"attempt", attempt+1,
				"maxRetries", maxRetries,
			)
		}

		if createErr != nil {
			log.Error(createErr, "failed to create tunnel CRD after all retries",
				"totalAttempts", maxRetries,
			)
			return
		}

		log.Info("tunnel CRD created successfully, waiting for reconciliation",
			"crdName", crdName,
			"tunnelName", tunnelName,
		)

		// Wait for tunnel to be reconciled and ready
		if err := waitForTunnelReady(ctx, mgr.GetClient(), crdName, operatorNs, log); err != nil {
			log.Error(err, "tunnel creation succeeded but failed to become ready",
				"crdName", crdName,
			)
			return
		}

		log.Info("default tunnel is ready and active",
			"crdName", crdName,
			"tunnelName", tunnelName,
		)
	}()

	return nil
}

// waitForTunnelReady waits for the tunnel to be reconciled and ready
func waitForTunnelReady(ctx context.Context, client client.Client, name, namespace string, log logr.Logger) error {
	// Poll for up to 2 minutes with 5 second intervals
	timeout := time.After(2 * time.Minute)
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("context cancelled while waiting for tunnel readiness")
		case <-timeout:
			return fmt.Errorf("timeout waiting for tunnel to become ready after 2 minutes")
		case <-ticker.C:
			tunnel := &tunnelsv1.CloudflareTunnel{}
			if err := client.Get(ctx, types.NamespacedName{
				Name:      name,
				Namespace: namespace,
			}, tunnel); err != nil {
				log.Error(err, "failed to get tunnel status")
				continue
			}

			// Check if tunnel is ready
			if tunnel.Status.Ready {
				log.Info("tunnel is ready",
					"tunnelID", tunnel.Status.TunnelID,
					"secret", tunnel.Status.TunnelSecret,
					"daemonReplicas", tunnel.Status.DaemonStatus.Replicas,
					"readyReplicas", tunnel.Status.DaemonStatus.ReadyReplicas,
				)
				return nil
			}

			// Log current status for debugging
			log.V(1).Info("waiting for tunnel to become ready",
				"ready", tunnel.Status.Ready,
				"tunnelID", tunnel.Status.TunnelID,
				"observedGeneration", tunnel.Status.ObservedGeneration,
			)
		}
	}
}
