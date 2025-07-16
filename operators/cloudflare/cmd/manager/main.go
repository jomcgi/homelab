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

// TunnelInitializer runs after the manager starts to initialize the tunnel
type TunnelInitializer struct {
	reconciler *controller.TunnelReconciler
	log        logr.Logger
}

func (t *TunnelInitializer) Start(ctx context.Context) error {
	// Wait a moment for the manager to be fully ready
	time.Sleep(3 * time.Second)
	
	t.log.Info("Initializing operator tunnel")
	if _, err := t.reconciler.Reconcile(ctx, ctrl.Request{}); err != nil {
		t.log.Error(err, "Failed to initialize tunnel")
		return err
	}
	
	t.log.Info("Tunnel initialization complete, TunnelInitializer shutting down")
	
	// Wait for shutdown signal, but don't do any more reconciliation
	<-ctx.Done()
	
	// The pre-delete hook will handle cleanup, so TunnelInitializer doesn't need to
	t.log.Info("TunnelInitializer received shutdown signal")
	
	return nil
}

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
}

// setupSignalHandlers sets up context-based shutdown handling for tunnel cleanup
func setupSignalHandlers(ctx context.Context, tunnelReconciler *controller.TunnelReconciler) {
	go func() {
		<-ctx.Done()
		setupLog.Info("🔄 SHUTDOWN HANDLER: Context canceled, starting tunnel cleanup")
		
		// Create a context with timeout for emergency cleanup
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 900*time.Second) // 15 minutes for cleanup
		defer cancel()
		
		setupLog.Info("🔄 SHUTDOWN HANDLER: Starting emergency tunnel cleanup with 15-minute timeout")
		
		// Perform emergency tunnel cleanup
		if err := tunnelReconciler.EmergencyCleanup(cleanupCtx); err != nil {
			setupLog.Error(err, "❌ SHUTDOWN HANDLER: Failed to clean up tunnel during emergency shutdown")
		} else {
			setupLog.Info("✅ SHUTDOWN HANDLER: Tunnel cleanup completed successfully")
		}
		
		setupLog.Info("🔄 SHUTDOWN HANDLER: Tunnel cleanup complete")
	}()
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

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                 scheme,
		Metrics:                metricsserver.Options{BindAddress: metricsAddr},
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "cloudflare-operator-leader-election",
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

	if err = (&controller.ServiceReconciler{
		Client:           mgr.GetClient(),
		Scheme:           mgr.GetScheme(),
		CloudflareClient: cfClient,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "Service")
		os.Exit(1)
	}

	// Get operator namespace
	operatorNamespace := os.Getenv("NAMESPACE")
	if operatorNamespace == "" {
		operatorNamespace = "cloudflare" // Default to cloudflare namespace
	}
	
	// Get operator pod name for ownership
	operatorPodName := os.Getenv("HOSTNAME")
	if operatorPodName == "" {
		operatorPodName = "cloudflare-operator-pod" // Fallback name
	}
	
	// Setup tunnel controller to manage operator's tunnel
	tunnelReconciler := &controller.TunnelReconciler{
		Client:           mgr.GetClient(),
		Scheme:           mgr.GetScheme(),
		CloudflareClient: cfClient,
		Namespace:        operatorNamespace,
		OperatorPodName:  operatorPodName,
	}
	
	// Register tunnel controller with manager to watch for secret events
	if err := tunnelReconciler.SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "Tunnel")
		os.Exit(1)
	}
	
	// Add a runnable to initialize tunnel after manager starts
	if err := mgr.Add(&TunnelInitializer{
		reconciler: tunnelReconciler,
		log:        setupLog,
	}); err != nil {
		setupLog.Error(err, "unable to add tunnel initializer")
		os.Exit(1)
	}

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	// Set up shutdown handling first
	ctx := ctrl.SetupSignalHandler()
	
	// Set up custom SIGTERM handler for tunnel cleanup that works with controller-runtime
	setupSignalHandlers(ctx, tunnelReconciler)
	
	setupLog.Info("starting manager")
	if err := mgr.Start(ctx); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}