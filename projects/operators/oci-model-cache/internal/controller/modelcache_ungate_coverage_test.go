package controller

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/go-logr/logr"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/client/interceptor"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
	"github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/config"
	sm "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/statemachine"
)

// makeCompletedJob returns a batchv1.Job in the Complete state, simulating a
// successful copy job.  The termination message is intentionally absent so the
// controller falls back to mc.Status fields rather than parsing a message.
func makeCompletedJob(name, namespace string) *batchv1.Job {
	return &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
		Status: batchv1.JobStatus{
			Conditions: []batchv1.JobCondition{
				{
					Type:               batchv1.JobComplete,
					Status:             corev1.ConditionTrue,
					LastTransitionTime: metav1.NewTime(time.Now()),
				},
			},
		},
	}
}

// TestUpdateStatusAndUngateWaiters_UngateError_SoftFail verifies that when
// ungateWaitingPods returns an error (e.g., pod List fails), the reconciler
// still returns a successful result without propagating that error.
//
// This tests the soft-fail path in updateStatusAndUngateWaiters:
//
//	if err := ungateWaitingPods(...); err != nil {
//	    log.Error(err, "Failed to ungate waiting pods")
//	    // Don't fail the reconcile — pods will be ungated on next reconcile
//	}
//	return result  // success from updateStatus
//
// To reach ungateWaitingPods the test must first make updateStatus() succeed.
// updateStatus() calls Status().Patch() with an SSA patch.  The SubResourcePatch
// interceptor is used to accept that patch without actually applying it, so the
// reconciler proceeds to call ungateWaitingPods, which then hits the injected
// List error.
func TestUpdateStatusAndUngateWaiters_UngateError_SoftFail(t *testing.T) {
	// A Syncing MC whose status fields satisfy the SyncComplete transition.
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:       "llama-ungate",
			Generation: 1,
		},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "bartowski/llama",
			Registry: "ghcr.io/jomcgi/models",
			Revision: "main",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:              sm.PhaseSyncing,
			SyncJobName:        "sync-job-done",
			ResolvedRef:        "ghcr.io/jomcgi/models/bartowski-llama:rev-main",
			Digest:             "sha256:abc123",
			ResolvedRevision:   "main",
			Format:             "safetensors",
			ObservedGeneration: 1,
		},
	}

	// The completed Job lives in the operator's working namespace.
	completedJob := makeCompletedJob("sync-job-done", "oci-model-cache")

	scheme := controllerScheme(t)

	podListErrInjected := false
	podListErr := errors.New("etcd: temporarily unavailable")

	c := fake.NewClientBuilder().
		WithScheme(scheme).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		WithObjects(mc, completedJob).
		WithInterceptorFuncs(interceptor.Funcs{
			// Accept the SSA status patch so updateStatus() returns nil error,
			// allowing execution to proceed to the ungateWaitingPods call.
			SubResourcePatch: func(
				ctx context.Context,
				cl client.Client,
				subResourceName string,
				obj client.Object,
				patch client.Patch,
				opts ...client.SubResourcePatchOption,
			) error {
				// Silently accept the patch — don't actually apply it.
				return nil
			},
			// Inject an error when ungateWaitingPods tries to list Pods.
			List: func(ctx context.Context, cl client.WithWatch, list client.ObjectList, opts ...client.ListOption) error {
				if _, ok := list.(*corev1.PodList); ok {
					podListErrInjected = true
					return podListErr
				}
				return cl.List(ctx, list, opts...)
			},
		}).
		Build()

	r := &ModelCacheReconciler{
		Client:     c,
		Scheme:     scheme,
		Resolver:   &fakeResolver{},
		Calculator: sm.NewModelCacheCalculator(logr.Discard()),
		Observer:   sm.NoOpObserver{},
		Config: config.Config{
			Namespace: "oci-model-cache",
			CopyImage: "ghcr.io/jomcgi/homelab/bazel/tools/hf2oci:main",
		},
	}

	// ModelCache is cluster-scoped — empty namespace in the request.
	req := ctrl.Request{NamespacedName: client.ObjectKey{Name: mc.Name}}
	result, err := r.Reconcile(context.Background(), req)

	// The core assertion: ungateWaitingPods failure is swallowed.
	// The reconcile must succeed even though pod ungating errored.
	require.NoError(t, err,
		"ungateWaitingPods error must be swallowed; reconcile should return success")

	// The result should be a non-error requeue (Ready state requeues after a long interval).
	assert.Greater(t, result.RequeueAfter, time.Duration(0),
		"result should have a positive RequeueAfter from the Ready state requeue interval")

	// Confirm that the pod list was actually attempted — proving we reached the
	// ungateWaitingPods call and exercised the soft-fail branch.
	assert.True(t, podListErrInjected,
		"pod List must have been attempted inside ungateWaitingPods")
}
