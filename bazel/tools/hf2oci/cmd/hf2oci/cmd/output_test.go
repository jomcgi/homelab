package cmd

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
)

func TestPrintJSONResultStructure(t *testing.T) {
	result := &copy.Result{
		Ref:       "ghcr.io/jomcgi/models/org-model:rev-main",
		Digest:    "sha256:abc123",
		Cached:    false,
		Repo:      "Org/Model",
		Revision:  "main",
		Format:    copy.FormatGGUF,
		FileCount: 3,
		TotalSize: 4812345678,
	}

	data, err := json.Marshal(result)
	require.NoError(t, err)

	// Round-trip: unmarshal into a generic map to verify JSON field names.
	var m map[string]any
	require.NoError(t, json.Unmarshal(data, &m))

	assert.Equal(t, "ghcr.io/jomcgi/models/org-model:rev-main", m["ref"])
	assert.Equal(t, "sha256:abc123", m["digest"])
	assert.Equal(t, false, m["cached"])
	assert.Equal(t, "Org/Model", m["repo"])
	assert.Equal(t, "main", m["revision"])
	assert.Equal(t, "gguf", m["format"])
	assert.Equal(t, float64(3), m["fileCount"])
	assert.Equal(t, float64(4812345678), m["totalSize"])

	// Verify digest is omitted when empty.
	result.Digest = ""
	data, err = json.Marshal(result)
	require.NoError(t, err)
	var m2 map[string]any
	require.NoError(t, json.Unmarshal(data, &m2))
	_, hasDigest := m2["digest"]
	assert.False(t, hasDigest, "digest should be omitted when empty")
}

func TestPrintJSONErrorStructure(t *testing.T) {
	// Transient error.
	transientData, _ := json.Marshal(jsonError{
		Error:     "connection refused",
		Permanent: false,
	})
	var m map[string]any
	require.NoError(t, json.Unmarshal(transientData, &m))
	assert.Equal(t, "connection refused", m["error"])
	assert.Equal(t, false, m["permanent"])

	// Permanent error.
	permData, _ := json.Marshal(jsonError{
		Error:     "not found (HTTP 404): repo missing",
		Permanent: true,
	})
	var m2 map[string]any
	require.NoError(t, json.Unmarshal(permData, &m2))
	assert.Equal(t, true, m2["permanent"])
}

func TestWriteJSONToFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "result.json")

	// Set outputFile for writeJSON, then restore.
	old := outputFile
	outputFile = path
	defer func() { outputFile = old }()

	writeJSON([]byte(`{"ref":"test"}`))

	data, err := os.ReadFile(path)
	require.NoError(t, err)
	assert.Equal(t, `{"ref":"test"}`, string(data))

	// Verify the .tmp file was cleaned up.
	_, err = os.Stat(path + ".tmp")
	assert.True(t, os.IsNotExist(err))
}

func TestWriteJSONFallsBackToStdout(t *testing.T) {
	// Point at a non-existent directory to force write failure.
	old := outputFile
	outputFile = "/nonexistent-dir/result.json"
	defer func() { outputFile = old }()

	// Capture stdout.
	r, w, err := os.Pipe()
	require.NoError(t, err)
	oldStdout := os.Stdout
	os.Stdout = w
	defer func() { os.Stdout = oldStdout }()

	writeJSON([]byte(`{"fallback":true}`))
	w.Close()

	buf := make([]byte, 256)
	n, _ := r.Read(buf)
	assert.Equal(t, `{"fallback":true}`, string(buf[:n]))
}
