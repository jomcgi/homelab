package controller

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// ttlScheme returns a runtime.Scheme with ModelCache registered.
func ttlScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	scheme := runtime.NewScheme()
	require.NoError(t, v1alpha1.AddToScheme(scheme))
	return scheme
}

// makeMC creates a ModelCache with a given TTL and creation timestamp.
func makeMC(name string, ttl time.Duration, createdAgo time.Duration) *v1alpha1.ModelCache {
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              name,
			Namespace:         "default",
			CreationTimestamp: metav1.NewTime(time.Now().Add(-createdAgo)),
		},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "bartowski/llama",
			Registry: "ghcr.io/jomcgi/models",
		},
	}
	if ttl > 0 {
		mc.Spec.TTL = &metav1.Duration{Duration: ttl}
	}
	return mc
}

// TestTTLSweeper_DeletesExpiredResources verifies that ModelCache objects older
// than their TTL are deleted by the sweeper.
func TestTTLSweeper_DeletesExpiredResources(t *testing.T) {
	expired := makeMC("expired-model", 1*time.Hour, 2*time.Hour) // created 2h ago, TTL=1h
	fresh := makeMC("fresh-model", 24*time.Hour, 1*time.Hour)    // created 1h ago, TTL=24h

	scheme := ttlScheme(t)
	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(expired, fresh).
		Build()

	sweeper := &TTLSweeper{
		Client:   fakeClient,
		Interval: time.Minute,
	}

	sweeper.sweep(context.Background())

	// Expired model should be gone
	var list v1alpha1.ModelCacheList
	require.NoError(t, fakeClient.List(context.Background(), &list))
	assert.Len(t, list.Items, 1, "only the non-expired resource should remain")
	assert.Equal(t, "fresh-model", list.Items[0].Name)
}

// TestTTLSweeper_LeavesNonExpiredAlone verifies resources that haven't hit
// their TTL are untouched.
func TestTTLSweeper_LeavesNonExpiredAlone(t *testing.T) {
	notYetExpired := makeMC("not-yet", 48*time.Hour, 1*time.Hour) // 1h old, TTL=48h

	scheme := ttlScheme(t)
	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(notYetExpired).
		Build()

	sweeper := &TTLSweeper{Client: fakeClient, Interval: time.Minute}
	sweeper.sweep(context.Background())

	var list v1alpha1.ModelCacheList
	require.NoError(t, fakeClient.List(context.Background(), &list))
	assert.Len(t, list.Items, 1, "non-expired resource should not be deleted")
}

// TestTTLSweeper_SkipsResourcesWithNoTTL verifies that resources without a TTL
// are never swept.
func TestTTLSweeper_SkipsResourcesWithNoTTL(t *testing.T) {
	noTTL := makeMC("no-ttl", 0, 365*24*time.Hour) // 1 year old, no TTL set

	scheme := ttlScheme(t)
	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(noTTL).
		Build()

	sweeper := &TTLSweeper{Client: fakeClient, Interval: time.Minute}
	sweeper.sweep(context.Background())

	var list v1alpha1.ModelCacheList
	require.NoError(t, fakeClient.List(context.Background(), &list))
	assert.Len(t, list.Items, 1, "resource with no TTL should never be swept")
}

// TestTTLSweeper_SkipsZeroTTL verifies that a TTL of exactly 0 is ignored
// (treated as "no TTL").
func TestTTLSweeper_SkipsZeroTTL(t *testing.T) {
	zeroTTL := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:              "zero-ttl",
			Namespace:         "default",
			CreationTimestamp: metav1.NewTime(time.Now().Add(-1 * time.Hour)),
		},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "bartowski/llama",
			Registry: "ghcr.io/jomcgi/models",
			TTL:      &metav1.Duration{Duration: 0},
		},
	}

	scheme := ttlScheme(t)
	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(zeroTTL).
		Build()

	sweeper := &TTLSweeper{Client: fakeClient, Interval: time.Minute}
	sweeper.sweep(context.Background())

	var list v1alpha1.ModelCacheList
	require.NoError(t, fakeClient.List(context.Background(), &list))
	assert.Len(t, list.Items, 1, "zero-duration TTL should be treated as no TTL")
}

// TestTTLSweeper_DeletesMultipleExpired verifies batches of expired resources
// are all deleted in a single sweep.
func TestTTLSweeper_DeletesMultipleExpired(t *testing.T) {
	ttl := 30 * time.Minute
	resources := []*v1alpha1.ModelCache{
		makeMC("expired-1", ttl, 60*time.Minute),
		makeMC("expired-2", ttl, 90*time.Minute),
		makeMC("expired-3", ttl, 120*time.Minute),
		makeMC("fresh", ttl, 10*time.Minute), // not yet expired
	}

	scheme := ttlScheme(t)
	builder := fake.NewClientBuilder().WithScheme(scheme)
	for _, r := range resources {
		builder = builder.WithObjects(r)
	}
	fakeClient := builder.Build()

	sweeper := &TTLSweeper{Client: fakeClient, Interval: time.Minute}
	sweeper.sweep(context.Background())

	var list v1alpha1.ModelCacheList
	require.NoError(t, fakeClient.List(context.Background(), &list))
	assert.Len(t, list.Items, 1, "only the fresh resource should remain")
	assert.Equal(t, "fresh", list.Items[0].Name)
}

// TestTTLSweeper_HandlesEmptyList verifies no panic when there are no resources.
func TestTTLSweeper_HandlesEmptyList(t *testing.T) {
	scheme := ttlScheme(t)
	fakeClient := fake.NewClientBuilder().WithScheme(scheme).Build()

	sweeper := &TTLSweeper{Client: fakeClient, Interval: time.Minute}

	// Should not panic or error
	assert.NotPanics(t, func() {
		sweeper.sweep(context.Background())
	})
}

// TestTTLSweeper_Start_StopsOnContextCancel verifies that Start() returns when
// the context is cancelled (no goroutine leak).
func TestTTLSweeper_Start_StopsOnContextCancel(t *testing.T) {
	scheme := ttlScheme(t)
	fakeClient := fake.NewClientBuilder().WithScheme(scheme).Build()

	sweeper := &TTLSweeper{Client: fakeClient, Interval: 10 * time.Millisecond}

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan error, 1)
	go func() {
		done <- sweeper.Start(ctx)
	}()

	cancel()

	select {
	case err := <-done:
		assert.NoError(t, err, "Start() should return nil on context cancellation")
	case <-time.After(2 * time.Second):
		t.Fatal("Start() did not return after context cancellation")
	}
}
