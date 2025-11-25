// Package main provides the controlflow CLI tool for generating type-safe
// state machines for Kubernetes operators.
package main

import (
	"os"

	"github.com/jomcgi/homelab/operator-controlflow/cmd/controlflow/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
