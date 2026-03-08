// Package main provides the hf2oci CLI for copying HuggingFace models to OCI registries.
package main

import (
	"os"

	"github.com/jomcgi/homelab/tools/hf2oci/cmd/hf2oci/cmd"
	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
)

func main() {
	if err := cmd.Execute(); err != nil {
		if copy.IsPermanent(err) {
			os.Exit(2)
		}
		os.Exit(1)
	}
}
