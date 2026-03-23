package cmd

import (
	"testing"

	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestResolveCmdArgsValidation verifies that resolveCmd enforces exactly one
// positional argument via cobra.ExactArgs(1).
func TestResolveCmdArgsValidation(t *testing.T) {
	argsValidator := resolveCmd.Args
	require.NotNil(t, argsValidator, "resolveCmd.Args should be set")

	tests := []struct {
		name    string
		args    []string
		wantErr bool
	}{
		{name: "no args", args: []string{}, wantErr: true},
		{name: "two args", args: []string{"Org/Repo", "extra"}, wantErr: true},
		{name: "three args", args: []string{"Org/Repo", "extra1", "extra2"}, wantErr: true},
		{name: "one arg (valid)", args: []string{"Org/Repo"}, wantErr: false},
		{name: "one arg with slash", args: []string{"NousResearch/Hermes-4.3-Llama-3-36B-AWQ"}, wantErr: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := argsValidator(resolveCmd, tt.args)
			if tt.wantErr {
				assert.Error(t, err, "expected argument validation error")
			} else {
				assert.NoError(t, err, "expected no argument validation error")
			}
		})
	}
}

// TestResolveCmdFlagDefaults verifies the default values for all flags.
func TestResolveCmdFlagDefaults(t *testing.T) {
	flags := resolveCmd.Flags()

	revision, err := flags.GetString("revision")
	require.NoError(t, err)
	assert.Equal(t, "main", revision, "revision should default to 'main'")

	registry, err := flags.GetString("registry")
	require.NoError(t, err)
	assert.Equal(t, "", registry, "registry should default to empty string")

	tag, err := flags.GetString("tag")
	require.NoError(t, err)
	assert.Equal(t, "", tag, "tag should default to empty string")
}

// TestResolveCmdRegistryRequired verifies that --registry is marked required.
func TestResolveCmdRegistryRequired(t *testing.T) {
	registryFlag := resolveCmd.Flags().Lookup("registry")
	require.NotNil(t, registryFlag, "registry flag must exist")

	annotations := registryFlag.Annotations
	_, required := annotations[cobra.BashCompOneRequiredFlag]
	assert.True(t, required, "registry flag must be marked required")
}

// TestResolveCmdHasOutputFlag verifies the resolve command inherits -o/--output
// from the root persistent flags.
func TestResolveCmdHasOutputFlag(t *testing.T) {
	// The output flag is a persistent flag on rootCmd, so it appears on all
	// subcommands via InheritedFlags.
	f := resolveCmd.InheritedFlags().Lookup("output")
	require.NotNil(t, f, "output flag must be inherited from root")
	assert.Equal(t, "text", f.DefValue, "output flag should default to 'text'")
}

// TestValidateOutputFormatAllValues covers all branches of validateOutputFormat.
func TestValidateOutputFormatAllValues(t *testing.T) {
	origFormat := outputFormat
	origFile := outputFile
	defer func() {
		outputFormat = origFormat
		outputFile = origFile
	}()

	tests := []struct {
		name    string
		format  string
		file    string
		wantErr string
	}{
		{
			name:   "text format is valid",
			format: "text",
			file:   "",
		},
		{
			name:   "json format is valid",
			format: "json",
			file:   "",
		},
		{
			name:    "unknown format returns error",
			format:  "xml",
			wantErr: `invalid --output "xml"`,
		},
		{
			name:    "empty format returns error",
			format:  "",
			wantErr: `invalid --output ""`,
		},
		{
			name:    "output-file without json returns error",
			format:  "text",
			file:    "/tmp/result.json",
			wantErr: "--output-file requires --output json",
		},
		{
			name:   "output-file with json and existing dir is valid",
			format: "json",
			file:   "/tmp/result.json",
		},
		{
			name:   "termination-log path is allowed without dir check",
			format: "json",
			file:   "/dev/termination-log",
		},
		{
			name:    "output-file with non-existent dir returns error",
			format:  "json",
			file:    "/nonexistent-dir/result.json",
			wantErr: `output file directory "/nonexistent-dir"`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			outputFormat = tt.format
			outputFile = tt.file

			err := validateOutputFormat()
			if tt.wantErr != "" {
				require.Error(t, err)
				assert.Contains(t, err.Error(), tt.wantErr)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}
