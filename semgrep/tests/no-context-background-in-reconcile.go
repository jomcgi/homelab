package tests

import (
	"context"

	ctrl "sigs.k8s.io/controller-runtime"
)

type MyReconciler struct{}

// ruleid: no-context-background-in-reconcile
func (r *MyReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// BAD: ignores the lifecycle context from the controller manager
	bgCtx := context.Background()
	_ = doWork(bgCtx)
	return ctrl.Result{}, nil
}

type GoodReconciler struct{}

// ok: passes the received context through
func (r *GoodReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	_ = doWork(ctx)
	return ctrl.Result{}, nil
}

// ok: context.Background() outside of Reconcile is fine
func setupManager() {
	ctx := context.Background()
	_ = ctx
}

func doWork(ctx context.Context) error { return nil }
