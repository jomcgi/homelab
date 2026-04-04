package cmd

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/spf13/cobra"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/copy"
	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
)

var (
	copyRegistry      string
	copyRevision      string
	copyTag           string
	copyModelDir      string
	copyFile          string
	copyIncludeMMProj bool
	copyMaxShardSize  string
	copyMaxParallel   int
	copyDryRun        bool
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

  # Split a large GGUF into 500MB shard layers (default)
  hf2oci copy bartowski/Hermes-4.3-36B-GGUF:Hermes-4.3-36B-IQ4_XS -r ghcr.io/jomcgi/models`,
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
	copyCmd.Flags().BoolVar(&copyIncludeMMProj, "include-mmproj", false, "Include mmproj GGUF (multimodal projector) alongside file-selected weights")
	copyCmd.Flags().StringVar(&copyMaxShardSize, "max-shard-size", "500M", "Max size per GGUF shard layer (e.g. 4G, 500M). 0 disables splitting.")
	copyCmd.Flags().IntVar(&copyMaxParallel, "max-parallel", 0, "Max concurrent layer uploads/downloads (0 = auto from GOMEMLIMIT, fallback 100)")
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

	parallel := copyMaxParallel
	if parallel <= 0 {
		if n := copy.AutoParallel(); n > 0 {
			parallel = n
			fmt.Fprintf(os.Stderr, "Auto-tuned parallelism: %d (from GOMEMLIMIT)\n", parallel)
		} else {
			parallel = 100
		}
	}

	opts := copy.Options{
		Repo:          repo,
		Registry:      copyRegistry,
		Revision:      copyRevision,
		Tag:           copyTag,
		ModelDir:      copyModelDir,
		File:          copyFile,
		IncludeMMProj: copyIncludeMMProj,
		MaxShardSize:  maxShard,
		MaxParallel:   parallel,
		DryRun:        copyDryRun,
		HFClient:      client,
	}

	// Transfer progress is always logged to stderr (visible in container logs
	// even when -o json directs structured output to the termination log).
	opts.OnShardProgress = func(index, total int, bytesRead, shardSize, overallRead, overallSize int64) {
		fmt.Fprintf(os.Stderr, "Shard %d/%d: %d/%d MB | Overall: %d/%d MB (%.0f%%)\n",
			index, total, bytesRead>>20, shardSize>>20,
			overallRead>>20, overallSize>>20, float64(overallRead)/float64(overallSize)*100)
	}
	// Legacy per-layer progress for non-split paths.
	opts.OnProgress = func(bytesRead, totalSize int64) {
		if totalSize > 0 {
			fmt.Fprintf(os.Stderr, "Transfer: %d/%d MB (%.0f%%)\n",
				bytesRead>>20, totalSize>>20, float64(bytesRead)/float64(totalSize)*100)
		} else {
			fmt.Fprintf(os.Stderr, "Transfer: %d MB\n", bytesRead>>20)
		}
	}

	// Info callbacks always log to stderr (visible in container logs even
	// when -o json directs structured output to the termination log).
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
