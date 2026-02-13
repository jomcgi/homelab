package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
	"github.com/jomcgi/homelab/tools/hf2oci/pkg/hf"
)

var (
	resolveRegistry string
	resolveRevision string
	resolveTag      string
)

var resolveCmd = &cobra.Command{
	Use:   "resolve <repo>",
	Short: "Check if a HuggingFace model exists in an OCI registry",
	Long: `Resolve lists the HuggingFace repo, classifies files, derives the OCI
reference, and checks whether the image already exists in the registry.

No files are downloaded and nothing is pushed.

Examples:
  # Check if a model is already cached
  hf2oci resolve Qwen/Qwen2.5-0.5B-Instruct-GGUF -r ghcr.io/jomcgi/models

  # JSON output for automation
  hf2oci resolve Qwen/Qwen2.5-0.5B-Instruct-GGUF -r ghcr.io/jomcgi/models -o json`,
	Args: cobra.ExactArgs(1),
	RunE: runResolve,
}

func init() {
	rootCmd.AddCommand(resolveCmd)

	resolveCmd.Flags().StringVarP(&resolveRegistry, "registry", "r", "", "Target OCI registry (required)")
	resolveCmd.Flags().StringVar(&resolveRevision, "revision", "main", "HuggingFace revision")
	resolveCmd.Flags().StringVarP(&resolveTag, "tag", "t", "", "Override OCI tag (default: rev-{revision[:12]})")

	resolveCmd.MarkFlagRequired("registry")
}

func runResolve(cmd *cobra.Command, args []string) error {
	if err := validateOutputFormat(); err != nil {
		return err
	}

	repo := args[0]

	var clientOpts []hf.Option
	if token := os.Getenv("HF_TOKEN"); token != "" {
		clientOpts = append(clientOpts, hf.WithToken(token))
	}
	client := hf.NewClient(clientOpts...)

	result, err := copy.Resolve(cmd.Context(), copy.ResolveOptions{
		Repo:     repo,
		Registry: resolveRegistry,
		Revision: resolveRevision,
		Tag:      resolveTag,
		HFClient: client,
	})
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
		fmt.Fprintf(os.Stderr, "Found: %s@%s\n", result.Ref, result.Digest)
	} else {
		fmt.Fprintf(os.Stderr, "Not found in registry\n")
	}
	fmt.Printf("%s\n", result.Ref)
	return nil
}
