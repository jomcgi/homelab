package main

import "os"

func main() {
	// ruleid: no-hardcoded-k8s-service-url
	url1 := "http://my-service.default.svc.cluster.local:8080"

	// ruleid: no-hardcoded-k8s-service-url
	url2 := envOr("ORCHESTRATOR_URL", "http://agent-orchestrator.agent-platform.svc.cluster.local:8080")

	// ruleid: no-hardcoded-k8s-service-url
	url3 := envOr("SIGNOZ_URL", "http://signoz.signoz.svc.cluster.local:8080")

	// ok: no-hardcoded-k8s-service-url
	url4 := os.Getenv("SERVICE_URL")

	// ok: no-hardcoded-k8s-service-url
	url5 := "http://example.com/api"

	// ok: no-hardcoded-k8s-service-url
	url6 := "http://localhost:8080"

	_, _, _, _, _, _ = url1, url2, url3, url4, url5, url6
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
