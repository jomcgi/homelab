// Package main provides tests for the agent-run CLI tool.
package main

import (
	"testing"

	"k8s.io/apimachinery/pkg/runtime/schema"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ---------------------------------------------------------------------------
// resolveTask
// ---------------------------------------------------------------------------

func TestResolveTask_IssueFlag(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })

	issueFlag = 42
	task, err := resolveTask(nil)
	require.NoError(t, err)
	assert.Contains(t, task, "#42")
	assert.Contains(t, task, "homelab")
}

func TestResolveTask_Args(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })
	issueFlag = 0

	task, err := resolveTask([]string{"fix", "the", "bug"})
	require.NoError(t, err)
	assert.Equal(t, "fix the bug", task)
}

func TestResolveTask_SingleArg(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })
	issueFlag = 0

	task, err := resolveTask([]string{"do something"})
	require.NoError(t, err)
	assert.Equal(t, "do something", task)
}

func TestResolveTask_NoArgsNoFlag_ReturnsError(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })
	issueFlag = 0

	_, err := resolveTask([]string{})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "task description")
}

func TestResolveTask_IssueFlag_TakesPrecedenceOverArgs(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })
	issueFlag = 7

	task, err := resolveTask([]string{"ignore this"})
	require.NoError(t, err)
	assert.Contains(t, task, "#7")
	assert.NotContains(t, task, "ignore this")
}

func TestResolveTask_IssueFlag_Zero_DoesNotUseIssue(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })
	issueFlag = 0

	task, err := resolveTask([]string{"my task"})
	require.NoError(t, err)
	assert.Equal(t, "my task", task)
}

func TestResolveTask_MultipleArgs_JoinedWithSpaces(t *testing.T) {
	orig := issueFlag
	t.Cleanup(func() { issueFlag = orig })
	issueFlag = 0

	task, err := resolveTask([]string{"a", "b", "c"})
	require.NoError(t, err)
	assert.Equal(t, "a b c", task)
}

// ---------------------------------------------------------------------------
// buildGooseCommand
// ---------------------------------------------------------------------------

func TestBuildGooseCommand_NoProfile(t *testing.T) {
	cmd := buildGooseCommand("do the thing", "")
	assert.Equal(t, []string{"goose", "run", "--text", "do the thing"}, cmd)
}

func TestBuildGooseCommand_NoProfile_StartsWithGooseRun(t *testing.T) {
	cmd := buildGooseCommand("task", "")
	assert.Equal(t, "goose", cmd[0])
	assert.Equal(t, "run", cmd[1])
}

func TestBuildGooseCommand_WithCIDebugProfile(t *testing.T) {
	cmd := buildGooseCommand("debug CI", "ci-debug")
	assert.Equal(t, "goose", cmd[0])
	assert.Equal(t, "run", cmd[1])
	assert.Contains(t, cmd, "--recipe")
	assert.Contains(t, cmd, "--no-profile")
	assert.Contains(t, cmd, "--params")

	recipeIdx := indexOf(cmd, "--recipe")
	require.Greater(t, recipeIdx, 0)
	assert.Contains(t, cmd[recipeIdx+1], "ci-debug.yaml")
}

func TestBuildGooseCommand_WithCodeFixProfile(t *testing.T) {
	cmd := buildGooseCommand("fix the code", "code-fix")
	recipeIdx := indexOf(cmd, "--recipe")
	require.Greater(t, recipeIdx, 0)
	assert.Contains(t, cmd[recipeIdx+1], "code-fix.yaml")
}

func TestBuildGooseCommand_WithResearchProfile(t *testing.T) {
	cmd := buildGooseCommand("research topic", "research")
	recipeIdx := indexOf(cmd, "--recipe")
	require.Greater(t, recipeIdx, 0)
	assert.Contains(t, cmd[recipeIdx+1], "research.yaml")
}

func TestBuildGooseCommand_WithBazelProfile(t *testing.T) {
	cmd := buildGooseCommand("fix build", "bazel")
	recipeIdx := indexOf(cmd, "--recipe")
	require.Greater(t, recipeIdx, 0)
	assert.Contains(t, cmd[recipeIdx+1], "bazel.yaml")
}

func TestBuildGooseCommand_TaskPassedAsParam_WithProfile(t *testing.T) {
	task := "implement feature X"
	cmd := buildGooseCommand(task, "ci-debug")
	paramsIdx := indexOf(cmd, "--params")
	require.Greater(t, paramsIdx, 0)
	assert.Contains(t, cmd[paramsIdx+1], task)
}

func TestBuildGooseCommand_TaskPassedAsText_WithoutProfile(t *testing.T) {
	task := "implement feature Y"
	cmd := buildGooseCommand(task, "")
	textIdx := indexOf(cmd, "--text")
	require.Greater(t, textIdx, 0)
	assert.Equal(t, task, cmd[textIdx+1])
}

func TestBuildGooseCommand_NoProfileFlag_NotPresent(t *testing.T) {
	cmd := buildGooseCommand("task", "")
	assert.NotContains(t, cmd, "--no-profile")
	assert.NotContains(t, cmd, "--recipe")
}

func TestBuildGooseCommand_WithProfile_NoTextFlag(t *testing.T) {
	cmd := buildGooseCommand("task", "code-fix")
	assert.NotContains(t, cmd, "--text")
}

func TestBuildGooseCommand_RecipePath_IsAbsolute(t *testing.T) {
	for profileName := range validProfiles {
		cmd := buildGooseCommand("task", profileName)
		recipeIdx := indexOf(cmd, "--recipe")
		require.Greater(t, recipeIdx, 0, "profile %s should have --recipe", profileName)
		recipePath := cmd[recipeIdx+1]
		assert.True(t, len(recipePath) > 0 && recipePath[0] == '/',
			"recipe path %q for profile %q should be absolute", recipePath, profileName)
	}
}

// ---------------------------------------------------------------------------
// validProfiles
// ---------------------------------------------------------------------------

func TestValidProfiles_ContainsAllExpectedProfiles(t *testing.T) {
	expected := []string{"ci-debug", "code-fix", "research", "bazel"}
	for _, p := range expected {
		_, ok := validProfiles[p]
		assert.True(t, ok, "expected profile %q to be in validProfiles", p)
	}
}

func TestValidProfiles_HasExactlyFourProfiles(t *testing.T) {
	assert.Len(t, validProfiles, 4)
}

func TestValidProfiles_RecipePathsContainProfileName(t *testing.T) {
	for name, path := range validProfiles {
		assert.NotEmpty(t, path, "profile %q must have a non-empty recipe path", name)
		assert.Contains(t, path, name+".yaml", "profile %q recipe path must contain %s.yaml", name, name)
	}
}

func TestValidProfiles_AllPathsUnderRecipesDir(t *testing.T) {
	for name, path := range validProfiles {
		assert.Contains(t, path, "recipes/", "profile %q path %q must be under recipes/", name, path)
	}
}

func TestValidProfiles_AllPathsEndInYAML(t *testing.T) {
	for name, path := range validProfiles {
		assert.True(t, len(path) > 5 && path[len(path)-5:] == ".yaml",
			"profile %q path %q must end in .yaml", name, path)
	}
}

// ---------------------------------------------------------------------------
// Constants and package-level variables
// ---------------------------------------------------------------------------

func TestNamespaceConstant(t *testing.T) {
	assert.Equal(t, "goose-sandboxes", namespace)
}

func TestTemplateNameConstant(t *testing.T) {
	assert.Equal(t, "goose-agent", templateName)
}

func TestSandboxClaimGVR_Group(t *testing.T) {
	assert.Equal(t, "extensions.agents.x-k8s.io", sandboxClaimGVR.Group)
}

func TestSandboxClaimGVR_Version(t *testing.T) {
	assert.Equal(t, "v1alpha1", sandboxClaimGVR.Version)
}

func TestSandboxClaimGVR_Resource(t *testing.T) {
	assert.Equal(t, "sandboxclaims", sandboxClaimGVR.Resource)
}

func TestSandboxClaimGVR_Full(t *testing.T) {
	expected := schema.GroupVersionResource{
		Group:    "extensions.agents.x-k8s.io",
		Version:  "v1alpha1",
		Resource: "sandboxclaims",
	}
	assert.Equal(t, expected, sandboxClaimGVR)
}

func TestSandboxGVR_Group(t *testing.T) {
	assert.Equal(t, "agents.x-k8s.io", sandboxGVR.Group)
}

func TestSandboxGVR_Version(t *testing.T) {
	assert.Equal(t, "v1alpha1", sandboxGVR.Version)
}

func TestSandboxGVR_Resource(t *testing.T) {
	assert.Equal(t, "sandboxes", sandboxGVR.Resource)
}

func TestSandboxGVR_Full(t *testing.T) {
	expected := schema.GroupVersionResource{
		Group:    "agents.x-k8s.io",
		Version:  "v1alpha1",
		Resource: "sandboxes",
	}
	assert.Equal(t, expected, sandboxGVR)
}

// ---------------------------------------------------------------------------
// Cobra flag registration
// ---------------------------------------------------------------------------

func TestRootCmd_IssueFlagRegistered(t *testing.T) {
	f := rootCmd.Flags().Lookup("issue")
	require.NotNil(t, f, "issue flag must be registered")
	assert.Equal(t, "0", f.DefValue, "issue flag must default to 0")
}

func TestRootCmd_ProfileFlagRegistered(t *testing.T) {
	f := rootCmd.Flags().Lookup("profile")
	require.NotNil(t, f, "profile flag must be registered")
	assert.Equal(t, "", f.DefValue, "profile flag must default to empty string")
}

func TestRootCmd_SilenceUsageEnabled(t *testing.T) {
	assert.True(t, rootCmd.SilenceUsage, "SilenceUsage must be true to avoid printing usage on run errors")
}

func TestRootCmd_HasRunEFunction(t *testing.T) {
	assert.NotNil(t, rootCmd.RunE, "rootCmd must have a RunE function")
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

func indexOf(slice []string, target string) int {
	for i, v := range slice {
		if v == target {
			return i
		}
	}
	return -1
}
