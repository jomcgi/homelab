package statemachine

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// =============================================================================
// ApplyStatus tests
// =============================================================================

func makeStatusMC(phase string) *v1alpha1.ModelCache {
	return &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "status-test",
			Namespace: "default",
		},
		Status: v1alpha1.ModelCacheStatus{Phase: phase},
	}
}

func TestApplyStatus_Pending_SetsPhase(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCachePending{resource: mc}

	updated := s.ApplyStatus()

	assert.Equal(t, PhasePending, updated.Status.Phase)
	// Original should not be mutated
	assert.Empty(t, mc.Status.Phase)
}

func TestApplyStatus_Resolving_SetsAllFields(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheResolving{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			Digest:           "sha256:abc123",
			ResolvedRevision: "main",
			Format:           "gguf",
			FileCount:        5,
			TotalSize:        1024,
		},
	}

	updated := s.ApplyStatus()

	assert.Equal(t, PhaseResolving, updated.Status.Phase)
	assert.Equal(t, "ghcr.io/jomcgi/models/llama:main", updated.Status.ResolvedRef)
	assert.Equal(t, "sha256:abc123", updated.Status.Digest)
	assert.Equal(t, "main", updated.Status.ResolvedRevision)
	assert.Equal(t, "gguf", updated.Status.Format)
	assert.Equal(t, 5, updated.Status.FileCount)
	assert.Equal(t, int64(1024), updated.Status.TotalSize)
}

func TestApplyStatus_Syncing_SetsAllFields(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheSyncing{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			Digest:           "sha256:abc123",
			ResolvedRevision: "main",
			Format:           "safetensors",
			FileCount:        10,
			TotalSize:        2048,
		},
		SyncJob: SyncJob{SyncJobName: "sync-job-xyz"},
	}

	updated := s.ApplyStatus()

	assert.Equal(t, PhaseSyncing, updated.Status.Phase)
	assert.Equal(t, "ghcr.io/jomcgi/models/llama:main", updated.Status.ResolvedRef)
	assert.Equal(t, "sync-job-xyz", updated.Status.SyncJobName)
	assert.Equal(t, int64(2048), updated.Status.TotalSize)
}

func TestApplyStatus_Ready_SetsAllFields(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheReady{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			Digest:           "sha256:deadbeef",
			ResolvedRevision: "main",
			Format:           "gguf",
			FileCount:        3,
			TotalSize:        512,
		},
	}

	updated := s.ApplyStatus()

	assert.Equal(t, PhaseReady, updated.Status.Phase)
	assert.Equal(t, "sha256:deadbeef", updated.Status.Digest)
	assert.Equal(t, "gguf", updated.Status.Format)
}

func TestApplyStatus_Failed_SetsAllFields(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheFailed{
		resource: mc,
		ErrorInfo: ErrorInfo{
			Permanent:    true,
			LastState:    PhasePending,
			ErrorMessage: "repo not found: 404",
		},
	}

	updated := s.ApplyStatus()

	assert.Equal(t, PhaseFailed, updated.Status.Phase)
	assert.True(t, updated.Status.Permanent)
	assert.Equal(t, PhasePending, updated.Status.LastState)
	assert.Equal(t, "repo not found: 404", updated.Status.ErrorMessage)
}

func TestApplyStatus_Unknown_SetsObservedPhase(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheUnknown{resource: mc, ObservedPhase: "SomeGarbagePhase"}

	updated := s.ApplyStatus()

	assert.Equal(t, PhaseUnknown, updated.Status.Phase)
	assert.Equal(t, "SomeGarbagePhase", updated.Status.ObservedPhase)
}

func TestApplyStatus_DoesNotMutateOriginal(t *testing.T) {
	mc := makeStatusMC("")
	original := mc.Status.Phase
	s := ModelCacheReady{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ref",
			Digest:           "sha256:abc",
			ResolvedRevision: "main",
			Format:           "gguf",
		},
	}

	_ = s.ApplyStatus()

	assert.Equal(t, original, mc.Status.Phase, "ApplyStatus must not mutate the original resource")
}

// =============================================================================
// SSAPatch tests
// =============================================================================

func TestSSAPatch_Pending_ReturnsApplyPatch(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCachePending{resource: mc}

	patch, err := SSAPatch(s)

	require.NoError(t, err)
	require.NotNil(t, patch)
}

// TestSSAPatch_Syncing_ReturnsApplyPatch tests the Syncing path in
// applyStateToStatus which sets SyncJobName in addition to all ResolveResult
// fields. This is the only state-specific path not covered by the other
// SSAPatch tests.
func TestSSAPatch_Syncing_ReturnsApplyPatch(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheSyncing{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "main",
			Format:           "safetensors",
			FileCount:        4,
			TotalSize:        2048,
		},
		SyncJob: SyncJob{SyncJobName: "sync-job-xyz"},
	}

	patch, err := SSAPatch(s)

	require.NoError(t, err)
	require.NotNil(t, patch)
}

func TestSSAPatch_Resolving_ReturnsApplyPatch(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheResolving{
		resource: mc,
		ResolveResult: ResolveResult{
			ResolvedRef:      "ghcr.io/jomcgi/models/llama:main",
			ResolvedRevision: "main",
			Format:           "gguf",
		},
	}

	patch, err := SSAPatch(s)

	require.NoError(t, err)
	require.NotNil(t, patch)
}

func TestSSAPatch_Failed_ReturnsApplyPatch(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheFailed{
		resource: mc,
		ErrorInfo: ErrorInfo{
			Permanent:    false,
			LastState:    PhasePending,
			ErrorMessage: "transient error",
		},
	}

	patch, err := SSAPatch(s)

	require.NoError(t, err)
	require.NotNil(t, patch)
}

func TestSSAPatch_Unknown_ReturnsApplyPatch(t *testing.T) {
	mc := makeStatusMC("")
	s := ModelCacheUnknown{resource: mc, ObservedPhase: "garbage"}

	patch, err := SSAPatch(s)

	require.NoError(t, err)
	require.NotNil(t, patch)
}

func TestSSAPatch_DoesNotMutateOriginal(t *testing.T) {
	mc := makeStatusMC(PhasePending)
	mc.Spec = v1alpha1.ModelCacheSpec{
		Repo:     "bartowski/llama",
		Registry: "ghcr.io/jomcgi/models",
		Revision: "main",
	}
	s := ModelCachePending{resource: mc}

	_, err := SSAPatch(s)
	require.NoError(t, err)

	// Original spec must not be cleared
	assert.Equal(t, "bartowski/llama", mc.Spec.Repo, "SSAPatch must not mutate the original resource spec")
}
