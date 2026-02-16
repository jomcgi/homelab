package cmd

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/spf13/cobra"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
)

var (
	copyRegistry     string
	copyRevision     string
	copyTag          string
	copyModelDir     string
	copyFile         string
	copyMaxShardSize string
	copyDryRun       bool
)

var copyCmd = &cobra.Command{
	Use:   "copy <repo>",
	Short: "Copy a HuggingFace model to an OCI registry",
	Long: `Download a HuggingFace model repository and push it as a multi-platform OCI
image to a container registry. Weight files are streamed directly into OCI
layers without temporary files on disk.

The OCI tag defaults to "rev-{revision[:12]}". Use --tag to override.

Environment:
  HF_TOKEN          HuggingFace API token for private repos
  Docker credentials are handled by the default keychain (~/.docker/config.json)

Examples:
  # Copy a public model
  hf2oci copy NousResearch/Hermes-4.3-Llama-3-36B-AWQ -r ghcr.io/jomcgi/models

  # Copy at a specific revision
  hf2oci copy Qwen/Qwen2.5-0.5B-Instruct-GGUF -r ghcr.io/jomcgi/models --revision 9217f5db79a2

  # Dry run to see what would be uploaded
  hf2oci copy NousResearch/Hermes-4.3-Llama-3-36B-AWQ -r ghcr.io/jomcgi/models --dry-run

  # Split a large GGUF into 4GB shard layers
  hf2oci copy bartowski/Hermes-4.3-36B-GGUF:Hermes-4.3-36B-IQ4_XS -r ghcr.io/jomcgi/models --max-shard-size 4G`,
	Args: cobra.ExactArgs(1),
	RunE: runCopy,
}

func init() {
	rootCmd.AddCommand(copyCmd)

	copyCmd.Flags().StringVarP(&copyRegistry, "registry", "r", "", "Target OCI registry (required)")
	copyCmd.Flags().StringVar(&copyRevision, "revision", "main", "HuggingFace revision")
	copyCmd.Flags().StringVarP(&copyTag, "tag", "t", "", "Override OCI tag (default: rev-{revision[:12]})")
	copyCmd.Flags().StringVar(&copyModelDir, "model-dir", "", "In-image model path (default: /)")
	copyCmd.Flags().StringVar(&copyFile, "file", "", "GGUF filename prefix selector (e.g. ModelName-Q4_K_M)")
	copyCmd.Flags().StringVar(&copyMaxShardSize, "max-shard-size", "4G", "Max size per GGUF shard layer (e.g. 4G, 500M). 0 disables splitting.")
	copyCmd.Flags().BoolVar(&copyDryRun, "dry-run", false, "List files without downloading or pushing")

	copyCmd.MarkFlagRequired("registry")
}

func runCopy(cmd *cobra.Command, args []string) error {
	if err := validateOutputFormat(); err != nil {
		return err
	}

	maxShard, err := parseByteSize(copyMaxShardSize)
	if err != nil {
		return fmt.Errorf("invalid --max-shard-size: %w", err)
	}

	repo := args[0]

	var clientOpts []hf.Option
	if token := os.Getenv("HF_TOKEN"); token != "" {
		clientOpts = append(clientOpts, hf.WithToken(token))
	}
	client := hf.NewClient(clientOpts...)

	opts := copy.Options{
		Repo:         repo,
		Registry:     copyRegistry,
		Revision:     copyRevision,
		Tag:          copyTag,
		ModelDir:     copyModelDir,
		File:         copyFile,
		MaxShardSize: maxShard,
		DryRun:       copyDryRun,
		HFClient:     client,
	}

	// Suppress progress callbacks in JSON mode for clean machine output.
	if outputFormat != "json" {
		opts.OnResolve = func(repo, revision string) {
			fmt.Fprintf(os.Stderr, "Resolving %s@%s...\n", repo, revision)
		}
		opts.OnClassified = func(configs, weights int, format copy.ModelFormat) {
			fmt.Fprintf(os.Stderr, "Found %d files (%d weights, %d configs) [%s]\n",
				configs+weights, weights, configs, format)
		}
		opts.OnTarget = func(ref string) {
			fmt.Fprintf(os.Stderr, "Target: %s\n", ref)
		}
		opts.OnCacheHit = func(digest string) {
			fmt.Fprintf(os.Stderr, "Checking registry... found (cached)\n")
		}
		opts.OnUploadConfig = func(count int) {
			fmt.Fprintf(os.Stderr, "Checking registry... not found\n")
			fmt.Fprintf(os.Stderr, "Uploading config layer (%d files)\n", count)
		}
		opts.OnUploadWeight = func(index, total int, filename string) {
			fmt.Fprintf(os.Stderr, "Streaming weight %d/%d: %s\n", index, total, filename)
		}
		opts.OnGGUFSplit = func(shards int, file string) {
			fmt.Fprintf(os.Stderr, "Splitting %s into %d shards\n", file, shards)
		}
	}

	result, err := copy.Copy(cmd.Context(), opts)
	if err != nil {
		if outputFormat == "json" {
			printJSONError(err)
		}
		return err
	}

	if outputFormat == "json" {
		return printJSON(result)
	}

	if result.Cached {
		fmt.Printf("%s@%s\n", result.Ref, result.Digest)
	} else if result.Digest != "" {
		fmt.Fprintf(os.Stderr, "Pushed: %s@%s\n", result.Ref, result.Digest)
		fmt.Printf("%s@%s\n", result.Ref, result.Digest)
	} else {
		// Dry run.
		fmt.Printf("%s\n", result.Ref)
	}

	return nil
}

// parseByteSize parses a human-readable byte size like "4G", "500M", "4GB", "4GiB", "0".
func parseByteSize(s string) (int64, error) {
	s = strings.TrimSpace(s)
	if s == "0" {
		return 0, nil
	}

	// Normalize: strip trailing "iB" or "B" so "4GB"/"4GiB" become "4G".
	upper := strings.ToUpper(s)
	switch {
	case strings.HasSuffix(upper, "IB"):
		s = s[:len(s)-2]
	case strings.HasSuffix(upper, "B") && len(s) > 1:
		s = s[:len(s)-1]
	}

	var multiplier int64 = 1
	upper = strings.ToUpper(s)
	switch {
	case strings.HasSuffix(upper, "G"):
		multiplier = 1 << 30
		s = s[:len(s)-1]
	case strings.HasSuffix(upper, "M"):
		multiplier = 1 << 20
		s = s[:len(s)-1]
	case strings.HasSuffix(upper, "K"):
		multiplier = 1 << 10
		s = s[:len(s)-1]
	}

	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("parsing %q: %w", s, err)
	}
	if n < 0 {
		return 0, fmt.Errorf("size must be non-negative: %s", s)
	}
	return n * multiplier, nil
}
