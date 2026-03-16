package controller

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/go-logr/logr/testr"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
	"github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/naming"
	sm "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/statemachine"
)

// =============================================================================
// Test fixtures & helpers
// =============================================================================

// controllerScheme registers all types needed by the reconciler.
func controllerScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	s := runtime.NewScheme()
	require.NoError(t, v1alpha1.AddToScheme(s))
	require.NoError(t, batchv1.AddToScheme(s))
	require.NoError(t, corev1.AddToScheme(s))
	return s
}

// mockResolver is a configurable stub for the Resolver interface.
type mockResolver struct {
	result *ResolveResult
	err    error
}

func (m *mockResolver) Resolve(_ context.Context, _, _, _, _ string) (*ResolveResult, error) {
	return m.result, m.err
}

// newTestReconciler builds a ModelCacheReconciler backed by a fake client.
// Objects passed are pre-seeded into the fake store.
func newTestReconciler(t *testing.T, resolver Resolver, objects ...client.Object) (*ModelCacheReconciler, client.Client) {
	t.Helper()
	s := controllerScheme(t)
	fc := fake.NewClientBuilder().
		WithScheme(s).
		WithObjects(objects...).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		Build()
	calc := sm.NewModelCacheCalculator(testr.New(t))
	r := &ModelCacheReconciler{
		Client:     fc,
		Scheme:     s,
		Resolver:   resolver,
		Calculator: calc,
		Observer:   sm.NoOpObserver{},
		Config:     minimalConfig(), // reused from job_builder_test.go
	}
	return r, fc
}

// reqFor returns a ctrl.Request pointing at mc.
func reqFor(mc *v1alpha1.ModelCache) ctrl.Request {
	return ctrl.Request{NamespacedName: client.ObjectKey{
		Namespace: mc.Namespace,
		Name:      mc.Name,
	}}
}

// pendingMC returns a fresh ModelCache with no phase (treated as Pending).
func pendingMC() *v1alpha1.ModelCache {
	return &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-model",
			Namespace: "default",
		},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "bartowski/Llama-3.2-1B-Instruct-GGUF",
			Registry: "ghcr.io/jomcgi/models",
			Revision: "main",
		},
	}
}

// resolvingMC returns a ModelCache in Resolving phase with all required status fields.
func resolvingMC() *v1alpha1.ModelCache {
	mc := pendingMC()
	mc.Status = v1alpha1.ModelCacheStatus{
		Phase:            sm.PhaseResolving,
		ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
		Digest:           "sha256:abc123def456",
		ResolvedRevision: "main",
		Format:           "gguf",
		FileCount:        3,
		TotalSize:        1024,
	}
	return mc
}

// syncingMC returns a ModelCache in Syncing phase with the given job name.
func syncingMC(jobName string) *v1alpha1.ModelCache {
	mc := resolvingMC()
	mc.Status.Phase = sm.PhaseSyncing
	mc.Status.SyncJobName = jobName
	return mc
}

// readyMC returns a ModelCache in Ready phase with all required status fields.
func readyMC() *v1alpha1.ModelCache {
	mc := resolvingMC()
	mc.Status.Phase = sm.PhaseReady
	return mc
}

// failedMC returns a ModelCache in Failed phase.
func failedMC(permanent bool) *v1alpha1.ModelCache {
	mc := pendingMC()
	mc.Status = v1alpha1.ModelCacheStatus{
		Phase:        sm.PhaseFailed,
		ErrorMessage: "repo not found",
		LastState:    sm.PhasePending,
		Permanent:    permanent,
	}
	return mc
}

// completedJob returns a batchv1.Job with a Complete condition.
func completedJob(name, namespace string) *batchv1.Job {
	return &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
		Status: batchv1.JobStatus{
			Conditions: []batchv1.JobCondition{
				{Type: batchv1.JobComplete, Status: corev1.ConditionTrue},
			},
		},
	}
}

// failedJobObj returns a batchv1.Job with a Failed condition and the given reason.
func failedJobObj(name, namespace, reason string) *batchv1.Job {
	return &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
		Status: batchv1.JobStatus{
			Conditions: []batchv1.JobCondition{
				{Type: batchv1.JobFailed, Status: corev1.ConditionTrue, Message: reason},
			},
		},
	}
}

// runningJob returns a batchv1.Job that is still active (no conditions).
func runningJob(name, namespace string) *batchv1.Job {
	return &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
		Status:     batchv1.JobStatus{Active: 1},
	}
}

// podWithTermMsg returns a Pod bearing a job-name label and a termination message.
func podWithTermMsg(jobName, namespace, termMsg string) *corev1.Pod {
	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName + "-pod",
			Namespace: namespace,
			Labels:    map[string]string{"job-name": jobName},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					Name: "hf2oci",
					State: corev1.ContainerState{
						Terminated: &corev1.ContainerStateTerminated{
							ExitCode: 0,
							Message:  termMsg,
						},
					},
				},
			},
		},
	}
}

// =============================================================================
// Reconcile: resource-not-found path
// =============================================================================

// TestReconcile_ResourceNotFound verifies that reconciling a missing resource
// returns a nil error without crashing (object was already deleted).
func TestReconcile_ResourceNotFound(t *testing.T) {
	r, _ := newTestReconciler(t, nil /* resolver never called */)

	result, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: client.ObjectKey{Name: "nonexistent"},
	})

	require.NoError(t, err)
	assert.Equal(t, ctrl.Result{}, result)
}

// =============================================================================
// VisitPending tests
// =============================================================================

// TestReconcile_Pending_TransientError verifies that a transient resolver error
// causes a short requeue without updating status.
func TestReconcile_Pending_TransientError(t *testing.T) {
	mc := pendingMC()
	resolver := &mockResolver{err: fmt.Errorf("network timeout")} // not a PermanentError
	r, _ := newTestReconciler(t, resolver, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 30*time.Second, result.RequeueAfter)
}

// TestReconcile_Pending_PermanentError verifies that a permanent resolver error
// transitions the resource to Failed and schedules a slow requeue.
func TestReconcile_Pending_PermanentError(t *testing.T) {
	mc := pendingMC()
	resolver := &mockResolver{
		err: &PermanentError{Err: fmt.Errorf("repository not found: 404")},
	}
	r, fc := newTestReconciler(t, resolver, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 5*time.Minute, result.RequeueAfter)

	// Status should be updated to Failed
	var updated v1alpha1.ModelCache
	require.NoError(t, fc.Get(context.Background(), client.ObjectKey{Name: mc.Name, Namespace: mc.Namespace}, &updated))
	assert.Equal(t, sm.PhaseFailed, updated.Status.Phase)
	assert.True(t, updated.Status.Permanent)
	assert.Contains(t, updated.Status.ErrorMessage, "repository not found")
}

// TestReconcile_Pending_CacheHit verifies that when the resolver finds the model
// already cached, the resource transitions directly to Ready.
func TestReconcile_Pending_CacheHit(t *testing.T) {
	mc := pendingMC()
	resolver := &mockResolver{
		result: &ResolveResult{
			Cached:    true,
			Ref:       "ghcr.io/jomcgi/models/llama:main",
			Digest:    "sha256:deadbeef",
			Revision:  "main",
			Format:    "gguf",
			FileCount: 2,
			TotalSize: 2048,
		},
	}
	r, _ := newTestReconciler(t, resolver, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Ready state has RequeueAfter = 6h
	assert.Equal(t, 6*time.Hour, result.RequeueAfter)
}

// TestReconcile_Pending_CacheMiss verifies that when the model is not cached,
// the resource transitions to Resolving so a copy Job can be created.
func TestReconcile_Pending_CacheMiss(t *testing.T) {
	mc := pendingMC()
	resolver := &mockResolver{
		result: &ResolveResult{
			Cached:    false,
			Ref:       "ghcr.io/jomcgi/models/llama:main",
			Digest:    "",
			Revision:  "main",
			Format:    "gguf",
			FileCount: 3,
			TotalSize: 1024,
		},
	}
	r, _ := newTestReconciler(t, resolver, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Resolving state has RequeueAfter = 10s
	assert.Equal(t, 10*time.Second, result.RequeueAfter)
}

// =============================================================================
// VisitResolving tests
// =============================================================================

// TestReconcile_Resolving_CreatesJob verifies that when in Resolving state,
// a copy Job is created and the resource transitions to Syncing.
func TestReconcile_Resolving_CreatesJob(t *testing.T) {
	mc := resolvingMC()
	r, fc := newTestReconciler(t, nil /* resolver not called in Resolving */, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Syncing state has RequeueAfter = 30s
	assert.Equal(t, 30*time.Second, result.RequeueAfter)

	// The copy Job should now exist in the operator namespace
	expectedJobName := naming.JobName(mc.Status.ResolvedRef)
	var job batchv1.Job
	require.NoError(t, fc.Get(context.Background(),
		client.ObjectKey{Namespace: minimalConfig().Namespace, Name: expectedJobName},
		&job,
	))
	assert.Equal(t, expectedJobName, job.Name)
}

// TestReconcile_Resolving_JobAlreadyExists verifies that if the copy Job already
// exists (e.g. duplicate reconcile), the reconciler gracefully transitions to
// Syncing without returning an error.
func TestReconcile_Resolving_JobAlreadyExists(t *testing.T) {
	mc := resolvingMC()
	expectedJobName := naming.JobName(mc.Status.ResolvedRef)
	existingJob := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      expectedJobName,
			Namespace: minimalConfig().Namespace,
		},
	}
	r, _ := newTestReconciler(t, nil, mc, existingJob)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 30*time.Second, result.RequeueAfter)
}

// =============================================================================
// VisitSyncing tests
// =============================================================================

// TestReconcile_Syncing_JobNotFound verifies that if the sync Job disappears
// while the resource is in Syncing state, the resource transitions to Failed.
func TestReconcile_Syncing_JobNotFound(t *testing.T) {
	const jobName = "main"
	mc := syncingMC(jobName)
	r, _ := newTestReconciler(t, nil, mc) // job NOT in fake client

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Failed state has RequeueAfter = 5m
	assert.Equal(t, 5*time.Minute, result.RequeueAfter)
}

// TestReconcile_Syncing_JobRunning verifies that while the sync Job is active,
// the reconciler requeues at the Syncing interval without changing state.
func TestReconcile_Syncing_JobRunning(t *testing.T) {
	cfg := minimalConfig()
	const jobName = "main"
	mc := syncingMC(jobName)
	job := runningJob(jobName, cfg.Namespace)
	r, _ := newTestReconciler(t, nil, mc, job)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 30*time.Second, result.RequeueAfter)
}

// TestReconcile_Syncing_JobFailed verifies that a failed sync Job causes the
// resource to transition to Failed with the Job's failure reason.
func TestReconcile_Syncing_JobFailed(t *testing.T) {
	cfg := minimalConfig()
	const jobName = "main"
	mc := syncingMC(jobName)
	job := failedJobObj(jobName, cfg.Namespace, "BackoffLimitExceeded")
	r, fc := newTestReconciler(t, nil, mc, job)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 5*time.Minute, result.RequeueAfter)

	// Status should reflect the failure reason
	var updated v1alpha1.ModelCache
	require.NoError(t, fc.Get(context.Background(), client.ObjectKey{Name: mc.Name, Namespace: mc.Namespace}, &updated))
	assert.Equal(t, sm.PhaseFailed, updated.Status.Phase)
	assert.Contains(t, updated.Status.ErrorMessage, "BackoffLimitExceeded")
}

// TestReconcile_Syncing_JobComplete_WithTermMsg verifies that a completed Job
// with a valid termination message transitions the resource to Ready, parsing
// the result from the termination log.
func TestReconcile_Syncing_JobComplete_WithTermMsg(t *testing.T) {
	cfg := minimalConfig()
	const jobName = "main"
	mc := syncingMC(jobName)

	job := completedJob(jobName, cfg.Namespace)
	termMsg := `{"ref":"ghcr.io/jomcgi/models/llama:main","digest":"sha256:newdigest","revision":"main","format":"gguf","fileCount":3,"totalSize":4096}`
	pod := podWithTermMsg(jobName, cfg.Namespace, termMsg)

	r, _ := newTestReconciler(t, nil, mc, job, pod)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Ready state has RequeueAfter = 6h
	assert.Equal(t, 6*time.Hour, result.RequeueAfter)
}

// TestReconcile_Syncing_JobComplete_NoTermMsg verifies that when the sync Job
// completes but no termination message is found, the controller falls back to
// existing status fields and still transitions to Ready.
func TestReconcile_Syncing_JobComplete_NoTermMsg(t *testing.T) {
	cfg := minimalConfig()
	const jobName = "main"
	mc := syncingMC(jobName)
	job := completedJob(jobName, cfg.Namespace)
	// No pod with termination message
	r, _ := newTestReconciler(t, nil, mc, job)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Falls back to existing status fields → Ready state
	assert.Equal(t, 6*time.Hour, result.RequeueAfter)
}

// =============================================================================
// VisitReady tests
// =============================================================================

// TestReconcile_Ready_SpecUnchanged verifies that a Ready resource with no spec
// changes simply requeues at the Ready interval.
func TestReconcile_Ready_SpecUnchanged(t *testing.T) {
	mc := readyMC()
	mc.Generation = 1
	mc.Status.ObservedGeneration = 1 // no change
	r, _ := newTestReconciler(t, nil, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 6*time.Hour, result.RequeueAfter)
}

// TestReconcile_Ready_SpecChanged verifies that a spec change while Ready
// triggers a Resync, transitioning back to Pending.
func TestReconcile_Ready_SpecChanged(t *testing.T) {
	mc := readyMC()
	mc.Generation = 2
	mc.Status.ObservedGeneration = 1 // generation advanced → spec changed
	r, _ := newTestReconciler(t, nil, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Pending state has RequeueAfter = 0
	assert.Equal(t, time.Duration(0), result.RequeueAfter)
}

// =============================================================================
// VisitFailed tests
// =============================================================================

// TestReconcile_Failed_Permanent verifies that a permanently failed resource
// stays in Failed state and requeues with a slow backoff.
func TestReconcile_Failed_Permanent(t *testing.T) {
	mc := failedMC(true /* permanent */)
	r, _ := newTestReconciler(t, nil, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	assert.Equal(t, 5*time.Minute, result.RequeueAfter)
}

// TestReconcile_Failed_NonPermanent verifies that a non-permanent failure
// retries by transitioning back to Pending.
func TestReconcile_Failed_NonPermanent(t *testing.T) {
	mc := failedMC(false /* non-permanent */)
	r, _ := newTestReconciler(t, nil, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// After Retry(), state is Pending → RequeueAfter = 0
	assert.Equal(t, time.Duration(0), result.RequeueAfter)
}

// TestReconcile_Failed_SpecChanged verifies that a spec change while in Failed
// state resets the resource to Pending even if the failure was permanent.
func TestReconcile_Failed_SpecChanged(t *testing.T) {
	mc := failedMC(true /* permanent, but spec changed overrides */)
	mc.Generation = 2
	mc.Status.ObservedGeneration = 1
	r, fc := newTestReconciler(t, nil, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Requeue immediately (not after a delay) to pick up the spec change
	assert.True(t, result.Requeue)

	// Status should be cleared back to Pending
	var updated v1alpha1.ModelCache
	require.NoError(t, fc.Get(context.Background(), client.ObjectKey{Name: mc.Name, Namespace: mc.Namespace}, &updated))
	assert.Equal(t, sm.PhasePending, updated.Status.Phase)
	assert.Empty(t, updated.Status.ErrorMessage)
	assert.False(t, updated.Status.Permanent)
}

// =============================================================================
// VisitUnknown tests
// =============================================================================

// TestReconcile_Unknown_ResetsToP ending verifies that an unrecognised status
// phase causes the resource to be reset to Pending.
func TestReconcile_Unknown_ResetsToP ending(t *testing.T) {
	mc := pendingMC()
	mc.Status.Phase = "SomeGarbagePhase"
	r, _ := newTestReconciler(t, nil, mc)

	result, err := r.Reconcile(context.Background(), reqFor(mc))

	require.NoError(t, err)
	// Reset → Pending → RequeueAfter = 0
	assert.Equal(t, time.Duration(0), result.RequeueAfter)
}

// =============================================================================
// podToModelCacheRequests tests
// =============================================================================

// TestPodToModelCacheRequests_NotAPod verifies that non-Pod objects produce no requests.
func TestPodToModelCacheRequests_NotAPod(t *testing.T) {
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "node-1"}}
	reqs := podToModelCacheRequests(context.Background(), node)
	assert.Nil(t, reqs)
}

// TestPodToModelCacheRequests_NoAnnotation verifies that pods without the
// waiting-for annotation produce no reconcile requests.
func TestPodToModelCacheRequests_NoAnnotation(t *testing.T) {
	pod := &corev1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "pod-1", Namespace: "default"}}
	reqs := podToModelCacheRequests(context.Background(), pod)
	assert.Nil(t, reqs)
}

// TestPodToModelCacheRequests_WithAnnotation verifies that a pod annotated with
// a ModelCache name maps to the correct reconcile request.
func TestPodToModelCacheRequests_WithAnnotation(t *testing.T) {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "pod-1",
			Namespace: "default",
			Annotations: map[string]string{
				"oci-model-cache.jomcgi.dev/waiting-for": "my-model",
			},
		},
	}
	reqs := podToModelCacheRequests(context.Background(), pod)
	require.Len(t, reqs, 1)
	assert.Equal(t, "my-model", reqs[0].NamespacedName.Name)
}

// =============================================================================
// IsPermanentError tests
// =============================================================================

// TestIsPermanentError_True verifies that PermanentError is detected correctly.
func TestIsPermanentError_True(t *testing.T) {
	err := &PermanentError{Err: fmt.Errorf("404 not found")}
	assert.True(t, IsPermanentError(err))
}

// TestIsPermanentError_False verifies that regular errors are not permanent.
func TestIsPermanentError_False(t *testing.T) {
	err := fmt.Errorf("transient network error")
	assert.False(t, IsPermanentError(err))
}

// TestIsPermanentError_NilError verifies that nil is not a permanent error.
func TestIsPermanentError_NilError(t *testing.T) {
	assert.False(t, IsPermanentError(nil))
}

// TestPermanentError_ErrorString verifies that PermanentError formats its
// underlying error message correctly.
func TestPermanentError_ErrorString(t *testing.T) {
	inner := fmt.Errorf("repo does not exist")
	pe := &PermanentError{Err: inner}
	assert.Equal(t, inner.Error(), pe.Error())
}

// TestPermanentError_Unwrap verifies that errors.Unwrap returns the inner error.
func TestPermanentError_Unwrap(t *testing.T) {
	inner := fmt.Errorf("inner")
	pe := &PermanentError{Err: inner}
	assert.Equal(t, inner, pe.Unwrap())
}
