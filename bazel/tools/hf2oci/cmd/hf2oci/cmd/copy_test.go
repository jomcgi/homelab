package cmd

import (
	"testing"

	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseByteSize(t *testing.T) {
	tests := []struct {
		input   string
		want    int64
		wantErr bool
	}{
		// Zero — special case, disables splitting
		{input: "0", want: 0},

		// Bare integer (no suffix) — treated as bytes
		{input: "1000", want: 1000},

		// Kibibyte (K / KB / KiB)
		{input: "1K", want: 1 << 10},
		{input: "1KB", want: 1 << 10},
		{input: "1KiB", want: 1 << 10},
		{input: "512K", want: 512 << 10},

		// Mebibyte (M / MB / MiB)
		{input: "1M", want: 1 << 20},
		{input: "1MB", want: 1 << 20},
		{input: "1MiB", want: 1 << 20},
		{input: "500M", want: 500 << 20},

		// Gibibyte (G / GB / GiB)
		{input: "1G", want: 1 << 30},
		{input: "1GB", want: 1 << 30},
		{input: "1GiB", want: 1 << 30},
		{input: "4G", want: 4 << 30},

		// Case-insensitive suffix
		{input: "2g", want: 2 << 30},
		{input: "256m", want: 256 << 20},
		{input: "8k", want: 8 << 10},

		// Whitespace is trimmed
		{input: "  512M  ", want: 512 << 20},

		// Error cases
		{input: "", wantErr: true},
		{input: "abc", wantErr: true},
		{input: "-1G", wantErr: true},
		// Fractional sizes cannot be parsed (ParseInt does not support floats)
		{input: "4.5G", wantErr: true},

		// Zero with a suffix — treated as 0 * multiplier = 0 (not the "0" fast path)
		{input: "0K", want: 0},
		{input: "0M", want: 0},
		{input: "0G", want: 0},

		// Terabyte and above are not recognised — suffix falls through to ParseInt
		// which fails because "T" is not a valid digit sequence.
		{input: "1T", wantErr: true},
		{input: "1TB", wantErr: true},
		{input: "1TiB", wantErr: true},

		// Whitespace-only string is an error
		{input: "   ", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := parseByteSize(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Errorf("parseByteSize(%q) = %d, want error", tt.input, got)
				}
				return
			}
			if err != nil {
				t.Errorf("parseByteSize(%q) returned unexpected error: %v", tt.input, err)
				return
			}
			if got != tt.want {
				t.Errorf("parseByteSize(%q) = %d, want %d", tt.input, got, tt.want)
			}
		})
	}
}

// TestCopyCmdArgsValidation verifies that copyCmd enforces exactly one
// positional argument via cobra.ExactArgs(1).
func TestCopyCmdArgsValidation(t *testing.T) {
	argsValidator := copyCmd.Args
	require.NotNil(t, argsValidator, "copyCmd.Args should be set")

	tests := []struct {
		name    string
		args    []string
		wantErr bool
	}{
		{name: "no args", args: []string{}, wantErr: true},
		{name: "two args", args: []string{"Org/Repo", "extra"}, wantErr: true},
		{name: "one arg (valid)", args: []string{"Org/Repo"}, wantErr: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := argsValidator(copyCmd, tt.args)
			if tt.wantErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

// TestCopyCmdFlagDefaults verifies the default values for all copy flags.
func TestCopyCmdFlagDefaults(t *testing.T) {
	flags := copyCmd.Flags()

	revision, err := flags.GetString("revision")
	require.NoError(t, err)
	assert.Equal(t, "main", revision, "revision should default to 'main'")

	maxShard, err := flags.GetString("max-shard-size")
	require.NoError(t, err)
	assert.Equal(t, "500M", maxShard, "max-shard-size should default to '500M'")

	maxParallel, err := flags.GetInt("max-parallel")
	require.NoError(t, err)
	assert.Equal(t, 0, maxParallel, "max-parallel should default to 0 (auto)")

	dryRun, err := flags.GetBool("dry-run")
	require.NoError(t, err)
	assert.False(t, dryRun, "dry-run should default to false")

	registry, err := flags.GetString("registry")
	require.NoError(t, err)
	assert.Equal(t, "", registry)

	tag, err := flags.GetString("tag")
	require.NoError(t, err)
	assert.Equal(t, "", tag)

	modelDir, err := flags.GetString("model-dir")
	require.NoError(t, err)
	assert.Equal(t, "", modelDir)

	file, err := flags.GetString("file")
	require.NoError(t, err)
	assert.Equal(t, "", file)
}

// TestCopyCmdRegistryRequired verifies that --registry is marked required.
func TestCopyCmdRegistryRequired(t *testing.T) {
	registryFlag := copyCmd.Flags().Lookup("registry")
	require.NotNil(t, registryFlag, "registry flag must exist")

	annotations := registryFlag.Annotations
	_, required := annotations[cobra.BashCompOneRequiredFlag]
	assert.True(t, required, "registry flag must be marked required")
}

// TestRunCopyInvalidMaxShardSize verifies that runCopy returns an error for
// invalid --max-shard-size before any network I/O is attempted.
func TestRunCopyInvalidMaxShardSize(t *testing.T) {
	origShardSize := copyMaxShardSize
	origFormat := outputFormat
	defer func() {
		copyMaxShardSize = origShardSize
		outputFormat = origFormat
	}()

	// Ensure output format is valid so the first failure is the shard size.
	outputFormat = "text"
	// "notabytes" cannot be parsed — parseByteSize must return an error and
	// runCopy must propagate it without touching the network.
	copyMaxShardSize = "notabytes"

	err := runCopy(copyCmd, []string{"Org/Repo"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid --max-shard-size")
}

// TestRunCopyInvalidOutputFormat verifies that runCopy returns an error for
// an unrecognised --output format before any network I/O is attempted.
func TestRunCopyInvalidOutputFormat(t *testing.T) {
	origFormat := outputFormat
	origShardSize := copyMaxShardSize
	defer func() {
		outputFormat = origFormat
		copyMaxShardSize = origShardSize
	}()

	// Reset shard size to a valid value so the first failure is the format check.
	copyMaxShardSize = "500M"
	outputFormat = "yaml" // not "text" or "json"

	err := runCopy(copyCmd, []string{"Org/Repo"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid --output")
}
