package main

import (
	"os"
	"path/filepath"
	"testing"
)

// TestMain intercepts re-invocations of the test binary used as a fake "git"
// subprocess. When FAKE_GIT_PROCESS=1 the binary acts as a fake git and exits
// immediately, preventing the test runner from running real tests in that
// subprocess.
func TestMain(m *testing.M) {
	if os.Getenv("FAKE_GIT_PROCESS") == "1" {
		runFakeGit()
		os.Exit(0)
	}
	os.Exit(m.Run())
}

// runFakeGit simulates git subcommand behavior. The expected argument layout
// mirrors exec.Command("git", "-C", gitRoot, subCmd, ...) so os.Args is:
//
//	[testBinary, "-C", gitRoot, subCmd, ...]
//
// Environment variables control behavior:
//   - FAKE_GIT_COMMIT_NOTHING=1 → git commit exits 1 (nothing to commit)
//   - FAKE_GIT_PUSH_FAIL=1      → git push exits 128 (push rejected)
func runFakeGit() {
	// os.Args = [testBinary, "-C", gitRoot, subCmd, ...]
	if len(os.Args) < 4 {
		os.Exit(0)
	}
	subCmd := os.Args[3]
	switch subCmd {
	case "commit":
		if os.Getenv("FAKE_GIT_COMMIT_NOTHING") == "1" {
			os.Exit(1) // simulates "nothing to commit, working tree clean"
		}
		os.Exit(0)
	case "push":
		if os.Getenv("FAKE_GIT_PUSH_FAIL") == "1" {
			os.Exit(128) // simulates push rejected / network failure
		}
		os.Exit(0)
	default: // "add" and unknown subcommands succeed
		os.Exit(0)
	}
}

// setupFakeGit creates a directory with the test binary symlinked as "git" and
// prepends it to PATH so that exec.Command("git", ...) invokes our fake.
// Any extra environment variable strings in "KEY=VALUE" form are also set.
func setupFakeGit(t *testing.T, extraEnv ...string) {
	t.Helper()

	testBin, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}

	fakeBinDir := t.TempDir()
	if err := os.Symlink(testBin, filepath.Join(fakeBinDir, "git")); err != nil {
		t.Fatalf("symlink fake git: %v", err)
	}

	t.Setenv("PATH", fakeBinDir+":"+os.Getenv("PATH"))
	t.Setenv("FAKE_GIT_PROCESS", "1")
	for _, kv := range extraEnv {
		for i := 0; i < len(kv); i++ {
			if kv[i] == '=' {
				t.Setenv(kv[:i], kv[i+1:])
				break
			}
		}
	}
}

// setupGitVars temporarily overrides the package-level git configuration vars.
func setupGitVars(t *testing.T, repo, root, branch string) {
	t.Helper()
	origRepo, origRoot, origBranch := gitRepo, gitRoot, gitBranch
	gitRepo, gitRoot, gitBranch = repo, root, branch
	t.Cleanup(func() { gitRepo, gitRoot, gitBranch = origRepo, origRoot, origBranch })
}

// TestGitCommit_SkipsWhenGitRepoIsEmpty verifies that gitCommit is a no-op
// (returns nil, runs no git commands) when gitRepo is unset.
func TestGitCommit_SkipsWhenGitRepoIsEmpty(t *testing.T) {
	setupGitVars(t, "", t.TempDir(), "main")
	if err := gitCommit("test: daily reset"); err != nil {
		t.Errorf("expected nil when gitRepo is empty, got: %v", err)
	}
}

// TestGitCommit_HappyPath verifies that gitCommit runs git add, commit, and
// push without error when all three subcommands succeed.
func TestGitCommit_HappyPath(t *testing.T) {
	setupFakeGit(t)
	setupGitVars(t, "https://example.com/repo.git", t.TempDir(), "main")

	if err := gitCommit("test: update data"); err != nil {
		t.Errorf("unexpected error from gitCommit: %v", err)
	}
}

// TestGitCommit_NothingToCommit verifies that when git commit exits with
// status 1 (the "nothing to commit" case), gitCommit does NOT return an error
// and continues to push. This test documents the fix for the args[3] bug:
// the condition was previously args[2] == "commit" which always evaluated to
// false because args[2] is gitRoot, not the subcommand.
func TestGitCommit_NothingToCommit(t *testing.T) {
	setupFakeGit(t, "FAKE_GIT_COMMIT_NOTHING=1")
	setupGitVars(t, "https://example.com/repo.git", t.TempDir(), "main")

	if err := gitCommit("test: nothing changed"); err != nil {
		t.Errorf("expected nil when git commit finds nothing to commit, got: %v", err)
	}
}

// TestGitCommit_PushFails verifies that a push failure is surfaced as an error.
func TestGitCommit_PushFails(t *testing.T) {
	setupFakeGit(t, "FAKE_GIT_PUSH_FAIL=1")
	setupGitVars(t, "https://example.com/repo.git", t.TempDir(), "main")

	if err := gitCommit("test: push will fail"); err == nil {
		t.Error("expected error when git push fails, got nil")
	}
}

// TestGitCommit_EmptyCommitMessage verifies that an empty commit message is
// accepted (git itself would reject it, but our fake git succeeds).
func TestGitCommit_EmptyCommitMessage(t *testing.T) {
	setupFakeGit(t)
	setupGitVars(t, "https://example.com/repo.git", t.TempDir(), "main")

	if err := gitCommit(""); err != nil {
		t.Errorf("unexpected error for empty commit message: %v", err)
	}
}
