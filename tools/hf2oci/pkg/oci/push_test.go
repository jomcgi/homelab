package oci

import (
	"bytes"
	"context"
	"io"
	"net/http/httptest"
	"testing"

	"github.com/google/go-containerregistry/pkg/name"
	"github.com/google/go-containerregistry/pkg/registry"
	v1 "github.com/google/go-containerregistry/pkg/v1"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestPushAndCheckExists(t *testing.T) {
	// Start in-memory registry.
	reg := registry.New()
	srv := httptest.NewServer(reg)
	defer srv.Close()

	host := srv.Listener.Addr().String()
	ref, err := name.ParseReference(host + "/test/model:v1")
	require.NoError(t, err)

	// Build a small test index.
	cfgLayer, err := ConfigLayer(map[string][]byte{
		"config.json": []byte(`{}`),
	}, "/models/test")
	require.NoError(t, err)

	weightData := bytes.Repeat([]byte("d"), 64)
	weightLayer := StreamingWeightLayer(io.NopCloser(bytes.NewReader(weightData)), int64(len(weightData)), "/models/test", "model.safetensors")

	idx, err := BuildIndex(cfgLayer, []v1.Layer{weightLayer}, nil)
	require.NoError(t, err)

	ctx := context.Background()

	// Before push: should not exist.
	_, exists, err := CheckExists(ctx, ref)
	require.NoError(t, err)
	assert.False(t, exists)

	// Push.
	digest, err := PushIndex(ctx, ref, idx)
	require.NoError(t, err)
	assert.NotEmpty(t, digest)
	assert.Contains(t, digest, "sha256:")

	// After push: should exist.
	cachedDigest, exists, err := CheckExists(ctx, ref)
	require.NoError(t, err)
	assert.True(t, exists)
	assert.Equal(t, digest, cachedDigest)

	// Verify we can pull it back.
	pulledIdx, err := remote.Index(ref)
	require.NoError(t, err)
	mf, err := pulledIdx.IndexManifest()
	require.NoError(t, err)
	assert.Len(t, mf.Manifests, 2, "should have 2 platform manifests")
}
