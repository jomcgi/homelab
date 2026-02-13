package naming

import (
	"crypto/sha256"
	"fmt"
	"strings"
)

// ModelCacheName derives a deterministic, DNS-safe Kubernetes resource name
// from a HuggingFace repo and revision. The name is unique per (repo, revision)
// pair and safe for use as a Kubernetes object name.
//
// Examples:
//
//	ModelCacheName("bartowski/Llama-3.2-1B-Instruct-GGUF", "main")
//	→ "bartowski-llama-3.2-1b-instruct-gguf-rev-main"
//
//	ModelCacheName("NousResearch/Very-Long-Model-Name-That-Exceeds-Limits", "abc123")
//	→ "nousresearch-very-long-model-name-that-excee-rev-abc12-a1b2c3d4"  (truncated + hash)
func ModelCacheName(repo, revision string) string {
	if revision == "" {
		revision = "main"
	}

	// Normalize: lowercase, replace / with -
	name := strings.ToLower(strings.ReplaceAll(repo, "/", "-"))

	// Truncate revision for readability
	rev := revision
	if len(rev) > 12 {
		rev = rev[:12]
	}

	full := fmt.Sprintf("%s-rev-%s", name, rev)

	// Kubernetes names must be <= 63 chars and DNS-safe
	if len(full) <= 63 {
		return sanitizeDNS(full)
	}

	// Truncate and add a hash suffix for uniqueness
	hash := sha256.Sum256([]byte(fmt.Sprintf("%s@%s", repo, revision)))
	suffix := fmt.Sprintf("%x", hash[:4]) // 8 hex chars
	maxPrefix := 63 - len(suffix) - 1     // -1 for the separator
	return sanitizeDNS(full[:maxPrefix]) + "-" + suffix
}

// sanitizeDNS ensures a string is a valid DNS subdomain label:
// lowercase alphanumeric and hyphens, no leading/trailing hyphens.
func sanitizeDNS(s string) string {
	var b strings.Builder
	for _, c := range s {
		switch {
		case c >= 'a' && c <= 'z', c >= '0' && c <= '9', c == '.':
			b.WriteRune(c)
		case c == '-' || c == '_' || c == '/':
			b.WriteByte('-')
			// skip anything else
		}
	}
	return strings.Trim(b.String(), "-.")
}
