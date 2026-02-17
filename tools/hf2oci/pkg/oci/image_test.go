package oci

import (
	"archive/tar"
	"bytes"
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

func TestConfigLayer(t *testing.T) {
	files := map[string][]byte{
		"config.json":    []byte(`{"model_type":"llama"}`),
		"tokenizer.json": []byte(`{"version":"1.0"}`),
	}

	layer, err := ConfigLayer(files, "/models/my-model")
	require.NoError(t, err)

	entries := extractTar(t, layer)
	assert.Contains(t, entries, "/models/my-model/config.json")
	assert.Contains(t, entries, "/models/my-model/tokenizer.json")
	assert.Equal(t, `{"model_type":"llama"}`, string(entries["/models/my-model/config.json"]))
}

func TestStreamingWeightLayer(t *testing.T) {
	data := bytes.Repeat([]byte("x"), 1024)
	body := io.NopCloser(bytes.NewReader(data))

	layer := StreamingWeightLayer(body, int64(len(data)), "/models/test", "weight.safetensors")

	// Read the layer to materialize it.
	rc, err := layer.Compressed()
	require.NoError(t, err)
	_, err = io.ReadAll(rc)
	require.NoError(t, err)
	rc.Close()

	// Verify we can get a digest after streaming.
	_, err = layer.Digest()
	require.NoError(t, err)
}

func TestStreamingSplitGGUFLayer(t *testing.T) {
	header := []byte("GGUF-HEADER-BYTES")
	tensorData := bytes.Repeat([]byte("t"), 2048)
	body := io.NopCloser(bytes.NewReader(tensorData))

	layer := StreamingSplitGGUFLayer(header, body, int64(len(tensorData)), "/models/test", "model-00001-of-00003.gguf")

	// Read the layer to materialize it.
	rc, err := layer.Compressed()
	require.NoError(t, err)
	_, err = io.ReadAll(rc)
	require.NoError(t, err)
	rc.Close()

	// Verify digest is available after streaming.
	_, err = layer.Digest()
	require.NoError(t, err)
}

func TestBuildIndex(t *testing.T) {
	// Start in-memory registry to verify index via push+pull (streaming layers
	// can't be inspected until consumed by remote.WriteIndex).
	reg := registry.New()
	srv := httptest.NewServer(reg)
	defer srv.Close()

	cfgFiles := map[string][]byte{
		"config.json": []byte(`{"test":true}`),
	}
	cfgLayer, err := ConfigLayer(cfgFiles, "/models/test")
	require.NoError(t, err)

	weightData := bytes.Repeat([]byte("w"), 256)
	weightBody := io.NopCloser(bytes.NewReader(weightData))
	weightLayer := StreamingWeightLayer(weightBody, int64(len(weightData)), "/models/test", "model.safetensors")

	annotations := map[string]string{
		"org.huggingface.repo":     "TestOrg/TestModel",
		"org.huggingface.revision": "abc123",
	}

	idx, err := BuildIndex(cfgLayer, []v1.Layer{weightLayer}, annotations)
	require.NoError(t, err)

	// Push to registry (consumes streams).
	host := srv.Listener.Addr().String()
	ref, err := name.ParseReference(host + "/test/build-index:latest")
	require.NoError(t, err)
	err = remote.WriteIndex(ref, idx)
	require.NoError(t, err)

	// Pull back and verify.
	pulledIdx, err := remote.Index(ref)
	require.NoError(t, err)
	mf, err := pulledIdx.IndexManifest()
	require.NoError(t, err)

	// Single-manifest index (model weights are architecture-independent).
	require.Len(t, mf.Manifests, 1)
	assert.Equal(t, "linux", mf.Manifests[0].Platform.OS)
	assert.Equal(t, "amd64", mf.Manifests[0].Platform.Architecture)

	// Verify annotations.
	assert.Equal(t, "TestOrg/TestModel", mf.Annotations["org.huggingface.repo"])
	assert.Equal(t, "abc123", mf.Annotations["org.huggingface.revision"])

	// Verify image has 2 layers (config + weight).
	img, err := pulledIdx.Image(mf.Manifests[0].Digest)
	require.NoError(t, err)
	layers, err := img.Layers()
	require.NoError(t, err)
	assert.Len(t, layers, 2)
}

func TestBuildIndexNoConfig(t *testing.T) {
	reg := registry.New()
	srv := httptest.NewServer(reg)
	defer srv.Close()

	weightData := bytes.Repeat([]byte("w"), 128)
	weightBody := io.NopCloser(bytes.NewReader(weightData))
	weightLayer := StreamingWeightLayer(weightBody, int64(len(weightData)), "/models/test", "model.gguf")

	idx, err := BuildIndex(nil, []v1.Layer{weightLayer}, nil)
	require.NoError(t, err)

	host := srv.Listener.Addr().String()
	ref, err := name.ParseReference(host + "/test/no-config:latest")
	require.NoError(t, err)
	err = remote.WriteIndex(ref, idx)
	require.NoError(t, err)

	pulledIdx, err := remote.Index(ref)
	require.NoError(t, err)
	mf, err := pulledIdx.IndexManifest()
	require.NoError(t, err)

	// Single image should have 1 layer (weight only).
	require.Len(t, mf.Manifests, 1)
	img, err := pulledIdx.Image(mf.Manifests[0].Digest)
	require.NoError(t, err)
	layers, err := img.Layers()
	require.NoError(t, err)
	assert.Len(t, layers, 1)
}

// extractTar reads a layer and returns a map of path -> content.
func extractTar(t *testing.T, layer v1.Layer) map[string]string {
	t.Helper()
	rc, err := layer.Uncompressed()
	require.NoError(t, err)
	defer rc.Close()

	result := make(map[string]string)
	tr := tar.NewReader(rc)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		require.NoError(t, err)
		assert.Equal(t, int64(0o644), int64(hdr.Mode), "file %s should have mode 0644", hdr.Name)
		data, err := io.ReadAll(tr)
		require.NoError(t, err)
		result[hdr.Name] = string(data)
	}
	return result
}
