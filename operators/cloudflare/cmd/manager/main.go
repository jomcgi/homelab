package main

import (
	"context"
	"flag"
	"os"
	"time"

	"github.com/go-logr/logr"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"

	cloudflareapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
	"github.com/jomcgi/homelab/operators/cloudflare/internal/controller"
)

var (
	scheme   = runtime.NewScheme()
	setupLog = ctrl.Log.WithName("setup")
)

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
}

// TunnelInitializer handles one-time tunnel setup at startup
type TunnelInitializer struct {
	tunnelReconciler *controller.TunnelReconciler
	log              logr.Logger
}

// Start initializes the tunnel and returns immediately
func (t *TunnelInitializer) Start(ctx context.Context) error {
	// Create a separate goroutine for initialization
	go func() {
		// Use a timeout context for initialization
		initCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		
		t.log.Info("Initializing operator tunnel")
		if _, err := t.tunnelReconciler.Reconcile(initCtx, ctrl.Request{}); err != nil {
			t.log.Error(err, "Failed to initialize tunnel")
			os.Exit(1)
		} else {
			t.log.Info("Tunnel initialization complete")
		}
	}()
	
	// Return immediately so we don't block the manager
	return nil
}

// CleanupManager handles graceful shutdown of resources
type CleanupManager struct {
	tunnelReconciler *controller.TunnelReconciler
	log              logr.Logger
}

// NeedLeaderElection implements manager.LeaderElectionRunnable
func (c *CleanupManager) NeedLeaderElection() bool {
	// Cleanup should run regardless of leader election
	return false
}

// Start waits for shutdown and performs cleanup
func (c *CleanupManager) Start(ctx context.Context) error {
	// Wait for shutdown signal
	<-ctx.Done()
	
	c.log.Info("🔄 Received shutdown signal, starting graceful cleanup")
	
	// Create a new context with timeout for cleanup
	// This ensures cleanup completes even if the parent context is cancelled
	cleanupCtx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	
	// Perform tunnel cleanup
	if err := c.tunnelReconciler.EmergencyCleanup(cleanupCtx); err != nil {
		c.log.Error(err, "❌ Failed to clean up tunnel during shutdown")
		// Return error to signal unsuccessful cleanup
		return err
	}
	
	c.log.Info("✅ Graceful cleanup completed successfully")
	return nil
}

func main() {
	var metricsAddr string
	var enableLeaderElection bool
	var probeAddr string
	flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "The address the metric endpoint binds to.")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "The address the probe endpoint binds to.")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false,
		"Enable leader election for controller manager. "+
			"Enabling this will ensure there is only one active controller manager.")
	opts := zap.Options{
		Development: true,
	}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

	// Set up the context that will be cancelled on SIGTERM/SIGINT
	ctx := ctrl.SetupSignalHandler()

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                 scheme,
		Metrics:                metricsserver.Options{BindAddress: metricsAddr},
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "cloudflare-operator-leader-election",
		// Add graceful shutdown timeout
		GracefulShutdownTimeout: &[]time.Duration{5 * time.Minute}[0],
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	// Initialize Cloudflare client
	cfClient, err := cloudflareapi.NewClient()
	if err != nil {
		setupLog.Error(err, "unable to create Cloudflare client")
		os.Exit(1)
	}

	// Set up service controller
	if err = (&controller.ServiceReconciler{
		Client:           mgr.GetClient(),
		Scheme:           mgr.GetScheme(),
		CloudflareClient: cfClient,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "Service")
		os.Exit(1)
	}

	// Get operator configuration
	operatorNamespace := os.Getenv("NAMESPACE")
	if operatorNamespace == "" {
		operatorNamespace = "cloudflare"
	}
	
	operatorPodName := os.Getenv("HOSTNAME")
	if operatorPodName == "" {
		operatorPodName = "cloudflare-operator-pod"
	}
	
	// Set up tunnel controller
	tunnelReconciler := &controller.TunnelReconciler{
		Client:           mgr.GetClient(),
		Scheme:           mgr.GetScheme(),
		CloudflareClient: cfClient,
		Namespace:        operatorNamespace,
		OperatorPodName:  operatorPodName,
	}
	
	if err := tunnelReconciler.SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "Tunnel")
		os.Exit(1)
	}
	
	// Add tunnel initializer (non-blocking)
	if err := mgr.Add(&TunnelInitializer{
		tunnelReconciler: tunnelReconciler,
		log:              setupLog.WithName("initializer"),
	}); err != nil {
		setupLog.Error(err, "unable to add tunnel initializer")
		os.Exit(1)
	}
	
	// Add cleanup manager for graceful shutdown
	if err := mgr.Add(&CleanupManager{
		tunnelReconciler: tunnelReconciler,
		log:              setupLog.WithName("cleanup"),
	}); err != nil {
		setupLog.Error(err, "unable to add cleanup manager")
		os.Exit(1)
	}

	// Set up health checks
	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	setupLog.Info("starting manager")
	if err := mgr.Start(ctx); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
	
	setupLog.Info("manager stopped gracefully")
}