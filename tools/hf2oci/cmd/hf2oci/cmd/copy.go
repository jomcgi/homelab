package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
)

var (
	copyRegistry string
	copyRevision string
	copyTag      string
	copyModelDir string
	copyDryRun   bool
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
  hf2oci copy NousResearch/Hermes-4.3-Llama-3-36B-AWQ -r ghcr.io/jomcgi/models --dry-run`,
	Args: cobra.ExactArgs(1),
	RunE: runCopy,
}

func init() {
	rootCmd.AddCommand(copyCmd)

	copyCmd.Flags().StringVarP(&copyRegistry, "registry", "r", "", "Target OCI registry (required)")
	copyCmd.Flags().StringVar(&copyRevision, "revision", "main", "HuggingFace revision")
	copyCmd.Flags().StringVarP(&copyTag, "tag", "t", "", "Override OCI tag (default: rev-{revision[:12]})")
	copyCmd.Flags().StringVar(&copyModelDir, "model-dir", "", "In-image model path (default: /models/{repo-name})")
	copyCmd.Flags().BoolVar(&copyDryRun, "dry-run", false, "List files without downloading or pushing")

	copyCmd.MarkFlagRequired("registry")
}

func runCopy(cmd *cobra.Command, args []string) error {
	if err := validateOutputFormat(); err != nil {
		return err
	}

	repo := args[0]

	var clientOpts []hf.Option
	if token := os.Getenv("HF_TOKEN"); token != "" {
		clientOpts = append(clientOpts, hf.WithToken(token))
	}
	client := hf.NewClient(clientOpts...)

	opts := copy.Options{
		Repo:     repo,
		Registry: copyRegistry,
		Revision: copyRevision,
		Tag:      copyTag,
		ModelDir: copyModelDir,
		DryRun:   copyDryRun,
		HFClient: client,
	}

	// Suppress progress callbacks in JSON mode for clean machine output.
	if OutputFormat != "json" {
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
	}

	result, err := copy.Copy(cmd.Context(), opts)
	if err != nil {
		if OutputFormat == "json" {
			printJSONError(err)
		}
		return err
	}

	if OutputFormat == "json" {
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
