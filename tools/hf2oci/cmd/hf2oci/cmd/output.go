package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/jomcgi/homelab/tools/hf2oci/pkg/copy"
)

// OutputFormat is the CLI output mode.
var OutputFormat string

// OutputFile is the optional file path for JSON output.
var OutputFile string

// writeJSON marshals data as JSON and writes it to OutputFile (if set) or stdout.
// If writing to OutputFile fails, it falls back to stdout.
func writeJSON(data []byte) {
	if OutputFile == "" {
		os.Stdout.Write(data)
		return
	}
	// /dev/termination-log (and other device files) don't support rename,
	// so write directly. For regular files, use atomic write-then-rename.
	if OutputFile == "/dev/termination-log" {
		if err := os.WriteFile(OutputFile, data, 0o644); err != nil {
			os.Stdout.Write(data)
		}
		return
	}
	tmp := OutputFile + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		os.Stdout.Write(data)
		return
	}
	if err := os.Rename(tmp, OutputFile); err != nil {
		os.Remove(tmp)
		os.Stdout.Write(data)
		return
	}
}

// printJSON marshals v as JSON and writes it via writeJSON.
func printJSON(v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	writeJSON(data)
	return nil
}

// jsonError is the JSON envelope for errors.
type jsonError struct {
	Error     string `json:"error"`
	Permanent bool   `json:"permanent"`
}

// printJSONError writes a structured error via writeJSON.
func printJSONError(err error) {
	data, _ := json.Marshal(jsonError{
		Error:     err.Error(),
		Permanent: copy.IsPermanent(err),
	})
	data = append(data, '\n')
	writeJSON(data)
}

func init() {
	rootCmd.PersistentFlags().StringVarP(&OutputFormat, "output", "o", "text", `Output format: "text" or "json"`)
	rootCmd.PersistentFlags().StringVarP(&OutputFile, "output-file", "O", "", "Write JSON output to file instead of stdout (requires -o json)")
}

// validateOutputFormat checks that --output is "text" or "json" and that
// --output-file is only used with --output json.
func validateOutputFormat() error {
	if OutputFormat != "text" && OutputFormat != "json" {
		return fmt.Errorf("invalid --output %q: must be \"text\" or \"json\"", OutputFormat)
	}
	if OutputFile != "" && OutputFormat != "json" {
		return fmt.Errorf("--output-file requires --output json")
	}
	if OutputFile != "" && OutputFile != "/dev/termination-log" {
		dir := filepath.Dir(OutputFile)
		if _, err := os.Stat(dir); err != nil {
			return fmt.Errorf("output file directory %q: %w", dir, err)
		}
	}
	return nil
}
