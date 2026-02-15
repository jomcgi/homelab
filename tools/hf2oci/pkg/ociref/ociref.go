// Package ociref provides pure naming functions for deriving OCI references
// from HuggingFace model repositories. It also provides a lightweight ref
// resolver that calls ModelInfo for smart naming without requiring Tree/Classify.
package ociref

import (
	"context"
	"fmt"
	"strings"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
)

// DeriveTag returns the OCI tag to use. If tag is non-empty it is returned as-is;
// otherwise it is derived from revision as "rev-{revision[:12]}".
func DeriveTag(tag, revision string) string {
	if tag != "" {
		return tag
	}
	rev := revision
	if len(rev) > 12 {
		rev = rev[:12]
	}
	return "rev-" + rev
}

// DeriveRepoName converts a HuggingFace repo name to an OCI repo path,
// preserving the org/model structure for cleaner registry organization.
// e.g. "NousResearch/Hermes-4.3-Llama-3-36B-AWQ" -> "nousresearch/hermes-4.3-llama-3-36b-awq"
func DeriveRepoName(repo string) string {
	return strings.ToLower(repo)
}

// DeriveVariantTag flattens a HuggingFace repo name into a valid OCI tag.
// Used for derivative models to encode the variant identity in the tag.
// e.g. "Emilio407/nllb-200-distilled-1.3B-4bit" -> "emilio407-nllb-200-distilled-1.3b-4bit"
func DeriveVariantTag(repo string) string {
	return strings.ToLower(strings.ReplaceAll(repo, "/", "-"))
}

// ResolveRef computes the full OCI reference for a HuggingFace model by calling
// ModelInfo to determine base model relationships. On failure, falls back to
// simple naming (repo path + rev tag).
func ResolveRef(ctx context.Context, client *hf.Client, repo, registry, revision string) string {
	if revision == "" {
		revision = "main"
	}

	var repoPath, ociTag string
	info, err := client.ModelInfo(ctx, repo)
	if err == nil && info.BaseModels != nil && len(info.BaseModels.Models) > 0 {
		// Derivative model: group under base model's repo path for layer dedup.
		repoPath = DeriveRepoName(info.BaseModels.Models[0].ID)
		ociTag = DeriveVariantTag(repo)
	} else {
		// Base model or ModelInfo unavailable: use repo directly.
		repoPath = DeriveRepoName(repo)
		ociTag = DeriveTag("", revision)
	}

	return fmt.Sprintf("%s/%s:%s", registry, repoPath, ociTag)
}
