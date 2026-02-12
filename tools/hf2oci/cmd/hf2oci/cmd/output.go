package cmd

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
)

// OutputFormat is the CLI output mode.
var OutputFormat string

// printJSON marshals v as JSON to stdout.
func printJSON(v any) error {
	enc := json.NewEncoder(os.Stdout)
	return enc.Encode(v)
}

// jsonError is the JSON envelope for errors.
type jsonError struct {
	Error     string `json:"error"`
	Permanent bool   `json:"permanent"`
}

// printJSONError writes a structured error to stdout and returns an
// already-handled sentinel so the caller can still set the exit code.
func printJSONError(err error) {
	enc := json.NewEncoder(os.Stdout)
	enc.Encode(jsonError{
		Error:     err.Error(),
		Permanent: copy.IsPermanent(err),
	})
}

func init() {
	rootCmd.PersistentFlags().StringVarP(&OutputFormat, "output", "o", "text", `Output format: "text" or "json"`)
}

// validateOutputFormat checks that --output is either "text" or "json".
func validateOutputFormat() error {
	if OutputFormat != "text" && OutputFormat != "json" {
		return fmt.Errorf("invalid --output %q: must be \"text\" or \"json\"", OutputFormat)
	}
	return nil
}
