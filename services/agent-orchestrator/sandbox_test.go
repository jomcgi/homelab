package main

import (
	"reflect"
	"testing"
)

func TestBuildGooseCommand_NoProfile(t *testing.T) {
	cmd := buildGooseCommand("fix the tests", "")
	expected := []string{"goose", "run", "--text", "fix the tests"}
	if !reflect.DeepEqual(cmd, expected) {
		t.Fatalf("expected %v, got %v", expected, cmd)
	}
}

func TestBuildGooseCommand_WithProfile(t *testing.T) {
	cmd := buildGooseCommand("fix the build", "ci-debug")
	expected := []string{
		"goose", "run",
		"--recipe", "/home/goose-agent/recipes/ci-debug.yaml",
		"--no-profile",
		"--params", "task_description=fix the build",
	}
	if !reflect.DeepEqual(cmd, expected) {
		t.Fatalf("expected %v, got %v", expected, cmd)
	}
}

func TestBuildGooseCommand_CodeFixProfile(t *testing.T) {
	cmd := buildGooseCommand("refactor auth", "code-fix")
	expected := []string{
		"goose", "run",
		"--recipe", "/home/goose-agent/recipes/code-fix.yaml",
		"--no-profile",
		"--params", "task_description=refactor auth",
	}
	if !reflect.DeepEqual(cmd, expected) {
		t.Fatalf("expected %v, got %v", expected, cmd)
	}
}
