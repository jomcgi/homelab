package main

import (
	"fmt"
	"testing"
)

func TestRunnerBaseURL(t *testing.T) {
	fqdn := "goose-sandbox-abc123.goose-sandboxes.svc.cluster.local"
	url := fmt.Sprintf("http://%s:8081", fqdn)
	expected := "http://goose-sandbox-abc123.goose-sandboxes.svc.cluster.local:8081"
	if url != expected {
		t.Errorf("url = %q, want %q", url, expected)
	}
}
