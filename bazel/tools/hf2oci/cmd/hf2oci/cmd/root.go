// Package cmd provides the CLI commands for hf2oci.
package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

// Verbose controls verbose output.
var Verbose bool

var rootCmd = &cobra.Command{
	Use:   "hf2oci",
	Short: "Copy HuggingFace models to OCI registries",
	Long: `hf2oci converts HuggingFace model repositories into multi-platform OCI images
and pushes them to arbitrary container registries.

Weight files are streamed directly into OCI layers without temporary files.
Config/tokenizer files are bundled into a shared base layer.

Example:
  hf2oci copy NousResearch/Hermes-4.3-Llama-3-36B-AWQ --registry ghcr.io/jomcgi/models`,
	SilenceUsage:  true,
	SilenceErrors: true,
}

// Execute runs the root command.
func Execute() error {
	if err := rootCmd.Execute(); err != nil {
		// Always print to stderr: in JSON mode, operational errors go via
		// printJSONError in the subcommand; but validation/CLI errors
		// (bad flags, missing args) must still be visible somewhere.
		fmt.Fprintln(os.Stderr, "Error:", err)
		return err
	}
	return nil
}

func init() {
	rootCmd.PersistentFlags().BoolVarP(&Verbose, "verbose", "v", false, "Enable verbose output")
	rootCmd.CompletionOptions.DisableDefaultCmd = true
}
