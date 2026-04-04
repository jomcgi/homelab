package cmd

import (
	"bytes"
	"io"
	"os"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestExecuteSuccess verifies that Execute() returns nil when the root command
// completes without error (e.g. --help which cobra always handles cleanly).
func TestExecuteSuccess(t *testing.T) {
	rootCmd.SetArgs([]string{"--help"})
	t.Cleanup(func() { rootCmd.SetArgs(nil) })

	// Discard cobra's help output to keep test logs clean.
	rootCmd.SetOut(io.Discard)
	t.Cleanup(func() { rootCmd.SetOut(os.Stdout) })

	err := Execute()
	assert.NoError(t, err)
}

// TestExecuteError verifies that Execute() writes "Error: <msg>" to stderr and
// returns the underlying error when rootCmd.Execute() encounters a CLI error
// (e.g. an unrecognised flag).
func TestExecuteError(t *testing.T) {
	rootCmd.SetArgs([]string{"--no-such-flag"})
	t.Cleanup(func() { rootCmd.SetArgs(nil) })

	// Capture os.Stderr so we can assert on the printed message.
	r, w, err := os.Pipe()
	require.NoError(t, err)
	oldStderr := os.Stderr
	os.Stderr = w

	execErr := Execute()

	// Close write end and restore stderr before draining the pipe.
	w.Close()
	os.Stderr = oldStderr

	var buf bytes.Buffer
	_, _ = io.Copy(&buf, r)
	r.Close()

	require.Error(t, execErr)
	assert.True(t, strings.HasPrefix(buf.String(), "Error:"),
		"stderr should start with 'Error:' but got: %q", buf.String())
	assert.Contains(t, buf.String(), execErr.Error())
}

// TestVerboseFlagDefault verifies that --verbose / -v is registered as a
// persistent flag on rootCmd with a default of false.
func TestVerboseFlagDefault(t *testing.T) {
	f := rootCmd.PersistentFlags().Lookup("verbose")
	require.NotNil(t, f, "verbose flag must be registered as a persistent flag")
	assert.Equal(t, "false", f.DefValue, "verbose flag should default to false")
	assert.Equal(t, "v", f.Shorthand, "verbose flag should have -v shorthand")
}

// TestCompletionCommandDisabled verifies that the default completion
// sub-command is disabled on rootCmd.
func TestCompletionCommandDisabled(t *testing.T) {
	assert.True(t, rootCmd.CompletionOptions.DisableDefaultCmd,
		"rootCmd.CompletionOptions.DisableDefaultCmd must be true")
}
