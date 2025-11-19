# Claude Code Configuration

This directory contains configuration for Claude Code on the web.

## SessionStart Hook

The repository includes a SessionStart hook that automatically sets up the build environment when you start a new Claude Code session.

### What the Hook Does

The hook script (`scripts/claude-session-start.sh`) performs the following setup tasks:

1. **Installs bazelisk** - Downloads and installs bazelisk to `~/.local/bin/`
   - Bazelisk automatically downloads the correct Bazel version from `.bazelversion`
   - Creates a `bazel` symlink for convenience

2. **Configures BuildBuddy** (optional) - Sets up remote build execution if API key is provided
   - Enables 80-core parallel builds via BuildBuddy RBE
   - Enables remote caching for faster incremental builds
   - Creates `user.bazelrc` with your API key (gitignored)

3. **Pre-downloads Bazel** - Triggers bazelisk to download Bazel in the background
   - The first bazel command is always slow, this avoids user waiting

4. **Persists environment variables** - Sets up PATH and Bazel config for subsequent commands
   - Adds `~/.local/bin` to PATH
   - Sets `BAZEL_USER_HOME` for proper caching

### Configuration

The hook is configured in `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/scripts/claude-session-start.sh"
          }
        ]
      }
    ]
  }
}
```

### Setting Up BuildBuddy Remote Execution (Optional)

To enable 80-core remote builds and caching via BuildBuddy:

1. **Get your BuildBuddy API key**:
   - Sign up at https://app.buildbuddy.io
   - Navigate to Settings → API Keys
   - Copy your organization's API key

2. **Add the API key to Claude Code**:
   - In Claude Code on the web, navigate to your environment settings
   - Add a new environment variable:
     ```
     BUILDBUDDY_API_KEY=your_api_key_here
     ```
   - Alternatively, add it to `.claude/settings.json`:
     ```json
     {
       "env": {
         "BUILDBUDDY_API_KEY": "your_api_key_here"
       }
     }
     ```

3. **Restart your session** - The SessionStart hook will detect the API key and configure BuildBuddy

### Without BuildBuddy

If you don't set up BuildBuddy, builds will run locally. The hook will still:
- Install bazelisk
- Set up the Bazel environment
- Work perfectly fine, just without remote execution

Local builds are great for:
- Small changes and quick iterations
- Testing locally before pushing
- Working offline

Remote builds (BuildBuddy) are better for:
- Large builds that benefit from parallelization
- CI/CD pipelines
- Shared caching across team members

### Verifying the Setup

After the SessionStart hook runs, you should see:

```bash
✅ bazelisk installed
✅ Bazel ready: Bazel 9 (rolling)
✅ Environment variables persisted
```

If BuildBuddy is configured:
```bash
✅ BuildBuddy configured for remote execution (80 cores)
```

You can then run Bazel commands:

```bash
bazel run //tools/format:format  # Format code and render manifests
bazel build //...                # Build all targets
bazel test //...                 # Run all tests
```

### Troubleshooting

**Bazelisk not found after hook runs**:
- Ensure `~/.local/bin` is in your PATH
- Run: `export PATH="$HOME/.local/bin:$PATH"`

**BuildBuddy not configured**:
- Check that `BUILDBUDDY_API_KEY` is set in environment
- Verify API key is correct
- Look for errors in the SessionStart hook output

**Bazel version issues**:
- The hook uses `.bazelversion` file in the repository root
- Bazelisk automatically downloads the specified version
- If you see version errors, check `.bazelversion` is correct

## Permissions

The `settings.json` file includes pre-approved permissions for common tools:
- Git operations (`git:*`)
- GitHub CLI (`gh:*`)
- Bazel and Bazelisk (`bazel:*`, `bazelisk:*`)
- Go tooling (`go build:*`, `go mod:*`, etc.)
- Documentation fetching from trusted domains

These permissions allow Claude Code to help you without requesting approval for each command.

## MCP Servers

The repository enables:
- All project-specific MCP servers
- Playwright MCP server for browser automation testing

## Cleanup

Sessions are automatically cleaned up after 60 days of inactivity.
