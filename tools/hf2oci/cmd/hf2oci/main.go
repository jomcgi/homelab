// Package main provides the hf2oci CLI for copying HuggingFace models to OCI registries.
package main

import (
	"os"

	"github.com/jomcgi/homelab/tools/hf2oci/cmd/hf2oci/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
