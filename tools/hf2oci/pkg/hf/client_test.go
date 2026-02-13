package hf

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestTree(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/api/models/NousResearch/Hermes-3-8B/tree/main", r.URL.Path)
		assert.Equal(t, "Bearer test-token", r.Header.Get("Authorization"))
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`[
			{"type":"file","path":"config.json","size":1234},
			{"type":"file","path":"model-00001-of-00002.safetensors","size":5000000000,"lfs":{"oid":"sha256:abc123","size":5000000000}},
			{"type":"file","path":"model-00002-of-00002.safetensors","size":3000000000,"lfs":{"oid":"sha256:def456","size":3000000000}},
			{"type":"file","path":"README.md","size":500}
		]`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithToken("test-token"))
	entries, err := c.Tree(context.Background(), "NousResearch/Hermes-3-8B", "main")
	require.NoError(t, err)

	assert.Len(t, entries, 4)
	assert.Equal(t, "config.json", entries[0].Path)
	assert.Nil(t, entries[0].LFS)
	assert.Equal(t, "model-00001-of-00002.safetensors", entries[1].Path)
	require.NotNil(t, entries[1].LFS)
	assert.Equal(t, "sha256:abc123", entries[1].LFS.OID)
	assert.Equal(t, int64(5000000000), entries[1].LFS.Size)
}

func TestTreeNotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`{"error":"Repository not found"}`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL))
	_, err := c.Tree(context.Background(), "nonexistent/repo", "main")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "not found (HTTP 404)")

	// checkResponse returns *APIError.
	var apiErr *APIError
	require.ErrorAs(t, err, &apiErr)
	assert.Equal(t, 404, apiErr.StatusCode)
	assert.True(t, apiErr.IsNotFound())
	assert.True(t, apiErr.IsClientError())
}

func TestTreeUnauthorized(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		w.Write([]byte(`{"error":"Unauthorized"}`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL))
	_, err := c.Tree(context.Background(), "private/repo", "main")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "HF_TOKEN")

	var apiErr *APIError
	require.ErrorAs(t, err, &apiErr)
	assert.Equal(t, 401, apiErr.StatusCode)
	assert.False(t, apiErr.IsNotFound())
	assert.True(t, apiErr.IsClientError())
}

func TestDownload(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/MyOrg/MyModel/resolve/main/config.json", r.URL.Path)
		w.Header().Set("Content-Length", "13")
		w.Write([]byte(`{"test":true}`))
	}))
	defer srv.Close()

	c := NewClient(WithBaseURL(srv.URL), WithToken("tok"))
	body, size, err := c.Download(context.Background(), "MyOrg/MyModel", "main", "config.json")
	require.NoError(t, err)
	defer body.Close()

	assert.Equal(t, int64(13), size)
	data, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.Equal(t, `{"test":true}`, string(data))
}

func TestDownloadAuthStrippedOnRedirect(t *testing.T) {
	// CDN server should NOT receive the auth header.
	cdn := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Empty(t, r.Header.Get("Authorization"), "auth header should be stripped on cross-domain redirect")
		w.Write([]byte("file-content"))
	}))
	defer cdn.Close()

	// HF server redirects to CDN.
	hf := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "Bearer my-token", r.Header.Get("Authorization"))
		http.Redirect(w, r, cdn.URL+"/cdn/file.safetensors", http.StatusFound)
	}))
	defer hf.Close()

	c := NewClient(WithBaseURL(hf.URL), WithToken("my-token"))
	body, _, err := c.Download(context.Background(), "org/model", "main", "file.safetensors")
	require.NoError(t, err)
	defer body.Close()

	data, err := io.ReadAll(body)
	require.NoError(t, err)
	assert.Equal(t, "file-content", string(data))
}
