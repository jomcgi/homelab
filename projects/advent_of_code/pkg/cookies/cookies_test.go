package cookies

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

// TestGetSession_EnvVar verifies that the AOC_SESSION env var takes priority.
func TestGetSession_EnvVar(t *testing.T) {
	t.Setenv("AOC_SESSION", "session-from-env")

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "session-from-env" {
		t.Errorf("GetSession() = %q, want %q", got, "session-from-env")
	}
}

// TestGetSession_DotEnv verifies that a .env file is read when AOC_SESSION is unset.
func TestGetSession_DotEnv(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	writeDotEnv(t, tmpDir, "AOC_SESSION=session-from-dotenv\n")
	chdirTemp(t, tmpDir)

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "session-from-dotenv" {
		t.Errorf("GetSession() = %q, want %q", got, "session-from-dotenv")
	}
}

// TestGetSession_DotEnvDoubleQuotes verifies that double-quoted values are unquoted.
func TestGetSession_DotEnvDoubleQuotes(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	writeDotEnv(t, tmpDir, `AOC_SESSION="quoted-value"`)
	chdirTemp(t, tmpDir)

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "quoted-value" {
		t.Errorf("GetSession() = %q, want %q", got, "quoted-value")
	}
}

// TestGetSession_DotEnvSingleQuotes verifies that single-quoted values are unquoted.
func TestGetSession_DotEnvSingleQuotes(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	writeDotEnv(t, tmpDir, "AOC_SESSION='single-quoted'")
	chdirTemp(t, tmpDir)

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "single-quoted" {
		t.Errorf("GetSession() = %q, want %q", got, "single-quoted")
	}
}

// TestGetSession_DotEnvMultipleVars verifies that the correct key is found
// among other unrelated keys.
func TestGetSession_DotEnvMultipleVars(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	content := "OTHER_VAR=other\nAOC_SESSION=found-session\nANOTHER=value\n"
	writeDotEnv(t, tmpDir, content)
	chdirTemp(t, tmpDir)

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "found-session" {
		t.Errorf("GetSession() = %q, want %q", got, "found-session")
	}
}

// TestGetSession_DotEnvWhitespaceLines verifies that blank lines and leading
// spaces on the key= line are handled (TrimSpace is applied per line).
func TestGetSession_DotEnvLeadingSpaces(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	// Lines with leading/trailing spaces around the key=value pair
	writeDotEnv(t, tmpDir, "  AOC_SESSION=spaced-value  \n")
	chdirTemp(t, tmpDir)

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "spaced-value" {
		t.Errorf("GetSession() = %q, want %q", got, "spaced-value")
	}
}

// TestGetSession_DotEnvEmptyValue verifies that an empty value falls through
// to ErrSessionNotSet.
func TestGetSession_DotEnvEmptyValue(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	writeDotEnv(t, tmpDir, "AOC_SESSION=\n")
	chdirTemp(t, tmpDir)

	_, err := GetSession()
	if !errors.Is(err, ErrSessionNotSet) {
		t.Errorf("GetSession() error = %v, want ErrSessionNotSet", err)
	}
}

// TestGetSession_NoDotEnvFile verifies that ErrSessionNotSet is returned when
// neither env var nor .env file is present.
func TestGetSession_NoDotEnvFile(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	chdirTemp(t, tmpDir)

	_, err := GetSession()
	if !errors.Is(err, ErrSessionNotSet) {
		t.Errorf("GetSession() error = %v, want ErrSessionNotSet", err)
	}
}

// TestGetSession_DotEnvNoMatchingKey verifies that a .env without AOC_SESSION
// returns ErrSessionNotSet.
func TestGetSession_DotEnvNoMatchingKey(t *testing.T) {
	t.Setenv("AOC_SESSION", "")

	tmpDir := t.TempDir()
	writeDotEnv(t, tmpDir, "UNRELATED=something\n")
	chdirTemp(t, tmpDir)

	_, err := GetSession()
	if !errors.Is(err, ErrSessionNotSet) {
		t.Errorf("GetSession() error = %v, want ErrSessionNotSet", err)
	}
}

// TestGetSession_EnvVarTakesPrecedenceOverDotEnv verifies that a non-empty
// AOC_SESSION env var wins over a conflicting .env entry.
func TestGetSession_EnvVarTakesPrecedenceOverDotEnv(t *testing.T) {
	t.Setenv("AOC_SESSION", "env-wins")

	tmpDir := t.TempDir()
	writeDotEnv(t, tmpDir, "AOC_SESSION=dotenv-loses\n")
	chdirTemp(t, tmpDir)

	got, err := GetSession()
	if err != nil {
		t.Fatalf("GetSession() error = %v, want nil", err)
	}
	if got != "env-wins" {
		t.Errorf("GetSession() = %q, want %q", got, "env-wins")
	}
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

func writeDotEnv(t *testing.T, dir, content string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, ".env"), []byte(content), 0o600); err != nil {
		t.Fatalf("writeDotEnv: %v", err)
	}
}

// chdirTemp changes the working directory to dir for the duration of the test
// and restores it afterwards.
func chdirTemp(t *testing.T, dir string) {
	t.Helper()
	orig, err := os.Getwd()
	if err != nil {
		t.Fatalf("Getwd: %v", err)
	}
	if err := os.Chdir(dir); err != nil {
		t.Fatalf("Chdir(%q): %v", dir, err)
	}
	t.Cleanup(func() {
		if err := os.Chdir(orig); err != nil {
			t.Errorf("Chdir back to %q: %v", orig, err)
		}
	})
}
