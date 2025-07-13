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
	
	// Keep running to handle tunnel lifecycle
	<-ctx.Done()
	
	// Cleanup tunnel on shutdown
	t.log.Info("Cleaning up tunnel on shutdown")
	if err := t.reconciler.CleanupTunnel(ctx); err != nil {
		t.log.Error(err, "Failed to cleanup tunnel")
	}
	
	return nil
}

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
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

	// Setup tunnel controller to manage operator's tunnel
	tunnelReconciler := &controller.TunnelReconciler{
		Client:           mgr.GetClient(),
		Scheme:           mgr.GetScheme(),
		CloudflareClient: cfClient,
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

	setupLog.Info("starting manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}