package config

import (
	"flag"
	"os"
	"time"
)

// Config holds operator configuration from flags and environment variables.
type Config struct {
	// Registry is the target OCI registry for cached models.
	Registry string

	// DefaultTTL is the default time-to-live for ModelCache resources.
	DefaultTTL time.Duration

	// CopyImage is the container image used for sync Jobs (hf2oci).
	CopyImage string

	// SyncServiceAccount is the Kubernetes service account for sync Jobs.
	SyncServiceAccount string

	// Namespace is the operator's namespace (from POD_NAMESPACE).
	Namespace string
}

// BindFlags registers config flags on the given FlagSet.
func (c *Config) BindFlags(fs *flag.FlagSet) {
	fs.StringVar(&c.Registry, "oci-registry", envOrDefault("OCI_REGISTRY", "ghcr.io/jomcgi/models"),
		"Target OCI registry for cached models")
	fs.DurationVar(&c.DefaultTTL, "default-ttl", 0,
		"Default TTL for ModelCache resources (0 = no expiry)")
	fs.StringVar(&c.CopyImage, "copy-image", envOrDefault("COPY_IMAGE", "ghcr.io/jomcgi/homelab/tools/hf2oci:latest"),
		"Container image for sync Jobs")
	fs.StringVar(&c.SyncServiceAccount, "sync-service-account", envOrDefault("SYNC_SERVICE_ACCOUNT", ""),
		"Service account for sync Jobs")
	c.Namespace = envOrDefault("POD_NAMESPACE", "oci-model-cache")
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
