// Command aoc is a CLI tool for Advent of Code puzzle management
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/cookies"
	"github.com/spf13/cobra"
)

// Answers stores verified answers for a puzzle
type Answers struct {
	Part1 *string `json:"part1,omitempty"`
	Part2 *string `json:"part2,omitempty"`
}

// loadAnswers reads answers.json from the day directory
func loadAnswers(dayDir string) (*Answers, error) {
	path := filepath.Join(dayDir, "answers.json")
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return &Answers{}, nil
		}
		return nil, err
	}
	var answers Answers
	if err := json.Unmarshal(data, &answers); err != nil {
		return nil, err
	}
	return &answers, nil
}

// saveAnswers writes answers.json to the day directory
func saveAnswers(dayDir string, answers *Answers) error {
	path := filepath.Join(dayDir, "answers.json")
	data, err := json.MarshalIndent(answers, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

var (
	rootDir    string
	sessionVar string
)

func main() {
	rootCmd := &cobra.Command{
		Use:   "aoc",
		Short: "Advent of Code CLI tool",
		Long:  "A CLI tool for downloading puzzle inputs, descriptions, and submitting solutions",
	}

	// Global flags
	rootCmd.PersistentFlags().StringVar(&rootDir, "dir", "", "Base directory for solutions (default: current directory)")
	rootCmd.PersistentFlags().StringVar(&sessionVar, "session", "", "AOC session cookie (or set AOC_SESSION env var)")

	// Commands
	rootCmd.AddCommand(todayCmd())
	rootCmd.AddCommand(getCmd())
	rootCmd.AddCommand(puzzleCmd())
	rootCmd.AddCommand(submitCmd())
	rootCmd.AddCommand(newCmd())
	rootCmd.AddCommand(initCmd())

	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

// getSession retrieves the AOC session cookie
func getSession() (string, error) {
	if sessionVar != "" {
		return sessionVar, nil
	}

	session, err := cookies.GetSession()
	if err != nil {
		return "", fmt.Errorf("%w\n\nTo get your session cookie:\n1. Log in to https://adventofcode.com\n2. Open browser DevTools (F12) → Application → Cookies\n3. Copy the 'session' cookie value\n4. Set: export AOC_SESSION=<value>", err)
	}
	return session, nil
}

// getDayDir returns the solution directory for a given year/day
func getDayDir(year, day int) string {
	dir := rootDir
	if dir == "" {
		dir = "advent_of_code"
	}
	return filepath.Join(dir, "solutions", fmt.Sprintf("year%d", year), fmt.Sprintf("day%02d", day))
}

// todayCmd sets up today's puzzle
func todayCmd() *cobra.Command {
	var lang string

	cmd := &cobra.Command{
		Use:   "today",
		Short: "Setup today's puzzle",
		Long:  "Download input, puzzle description, and create template for today (December only)",
		RunE: func(cmd *cobra.Command, args []string) error {
			day := aoc.CurrentDay()
			if day == 0 {
				return fmt.Errorf("today is not a valid Advent of Code day (must be December 1-25)")
			}
			year := aoc.CurrentYear()

			return setupDay(year, day, lang)
		},
	}

	cmd.Flags().StringVarP(&lang, "lang", "l", "both", "Language for solution template (go, python, both)")
	return cmd
}

// getCmd downloads puzzle input
func getCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "get [year] [day]",
		Short: "Download puzzle input",
		Long:  "Download the puzzle input for the specified year and day",
		Args:  cobra.MaximumNArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			year, day, err := parseYearDay(args)
			if err != nil {
				return err
			}

			session, err := getSession()
			if err != nil {
				return err
			}

			client := aoc.NewClient(session)

			if !aoc.IsPuzzleAvailable(year, day) {
				return fmt.Errorf("puzzle for %d day %d is not yet available", year, day)
			}

			dayDir := getDayDir(year, day)
			if err := os.MkdirAll(dayDir, 0o755); err != nil {
				return err
			}

			// Download input
			input, err := client.GetInput(year, day)
			if err != nil {
				return fmt.Errorf("failed to download input: %w", err)
			}
			inputPath := filepath.Join(dayDir, "input.txt")
			if err := os.WriteFile(inputPath, []byte(input), 0o644); err != nil {
				return err
			}
			fmt.Printf("Downloaded input to %s\n", inputPath)

			return nil
		},
	}
	return cmd
}

// puzzleCmd downloads the puzzle description as markdown
func puzzleCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "puzzle [year] [day]",
		Short: "Download puzzle description",
		Long:  "Download the puzzle description as markdown for the specified year and day",
		Args:  cobra.MaximumNArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			year, day, err := parseYearDay(args)
			if err != nil {
				return err
			}

			session, err := getSession()
			if err != nil {
				return err
			}

			client := aoc.NewClient(session)
			dayDir := getDayDir(year, day)

			if err := os.MkdirAll(dayDir, 0o755); err != nil {
				return err
			}

			// Download puzzle markdown
			markdown, err := client.GetPuzzleMarkdown(year, day)
			if err != nil {
				return fmt.Errorf("failed to download puzzle: %w", err)
			}
			puzzlePath := filepath.Join(dayDir, "puzzle.md")
			if err := os.WriteFile(puzzlePath, []byte(markdown), 0o644); err != nil {
				return err
			}
			fmt.Printf("Downloaded puzzle to %s\n", puzzlePath)

			return nil
		},
	}
	return cmd
}

// submitCmd submits an answer
func submitCmd() *cobra.Command {
	var part int
	var force bool

	cmd := &cobra.Command{
		Use:   "submit <answer> [year] [day]",
		Short: "Submit an answer",
		Long:  "Submit an answer for the specified puzzle part. Use --force to save answers for already-completed puzzles.",
		Args:  cobra.RangeArgs(1, 3),
		RunE: func(cmd *cobra.Command, args []string) error {
			answer := args[0]

			// Parse year/day from remaining args
			yearDayArgs := args[1:]
			year, day, err := parseYearDay(yearDayArgs)
			if err != nil {
				return err
			}

			if part < 1 || part > 2 {
				return fmt.Errorf("part must be 1 or 2")
			}

			session, err := getSession()
			if err != nil {
				return err
			}

			client := aoc.NewClient(session)

			fmt.Printf("Submitting answer '%s' for %d Day %d Part %d...\n", answer, year, day, part)

			result, err := client.Submit(year, day, part, answer)
			if err != nil {
				return fmt.Errorf("failed to submit: %w", err)
			}

			if result.TooSoon {
				fmt.Printf("⏳ Rate limited! Wait %s before submitting again.\n", result.WaitTime)
				return nil
			}

			if result.Correct {
				fmt.Println("⭐ Correct!")
				dayDir := getDayDir(year, day)

				// Save verified answer
				answers, err := loadAnswers(dayDir)
				if err != nil {
					fmt.Printf("Warning: could not load answers: %v\n", err)
					answers = &Answers{}
				}
				if part == 1 {
					answers.Part1 = &answer
				} else {
					answers.Part2 = &answer
				}
				if err := saveAnswers(dayDir, answers); err != nil {
					fmt.Printf("Warning: could not save answers: %v\n", err)
				} else {
					fmt.Printf("Saved answer to %s\n", filepath.Join(dayDir, "answers.json"))
				}

				// Generate test files
				if err := generateTests(dayDir, year, day); err != nil {
					fmt.Printf("Warning: could not generate tests: %v\n", err)
				}

				// If part 1, fetch part 2
				if part == 1 {
					fmt.Println("\nFetching Part 2...")
					markdown, err := client.GetPuzzleMarkdown(year, day)
					if err == nil {
						puzzlePath := filepath.Join(dayDir, "puzzle.md")
						os.WriteFile(puzzlePath, []byte(markdown), 0o644)
						fmt.Printf("Updated puzzle.md with Part 2\n")
					}
				}
			} else if strings.Contains(result.Message, "Already completed") {
				fmt.Println("✅ Already completed!")
				if force {
					fmt.Println("Saving answer for tests (--force)...")
					dayDir := getDayDir(year, day)

					answers, err := loadAnswers(dayDir)
					if err != nil {
						fmt.Printf("Warning: could not load answers: %v\n", err)
						answers = &Answers{}
					}
					if part == 1 {
						answers.Part1 = &answer
					} else {
						answers.Part2 = &answer
					}
					if err := saveAnswers(dayDir, answers); err != nil {
						fmt.Printf("Warning: could not save answers: %v\n", err)
					} else {
						fmt.Printf("Saved answer to %s\n", filepath.Join(dayDir, "answers.json"))
					}

					// Generate test files
					if err := generateTests(dayDir, year, day); err != nil {
						fmt.Printf("Warning: could not generate tests: %v\n", err)
					}
				} else {
					fmt.Println("Use --force to save this answer for tests (unverified)")
				}
			} else {
				fmt.Printf("❌ Incorrect: %s\n", result.Message)
			}

			return nil
		},
	}

	cmd.Flags().IntVarP(&part, "part", "p", 1, "Puzzle part (1 or 2)")
	cmd.Flags().BoolVarP(&force, "force", "f", false, "Save answer for already-completed puzzles (unverified)")
	return cmd
}

// newCmd creates a new day's solution structure
func newCmd() *cobra.Command {
	var lang string

	cmd := &cobra.Command{
		Use:   "new [year] [day]",
		Short: "Create solution template",
		Long:  "Create a new solution template for the specified year and day",
		Args:  cobra.MaximumNArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			year, day, err := parseYearDay(args)
			if err != nil {
				return err
			}

			return setupDay(year, day, lang)
		},
	}

	cmd.Flags().StringVarP(&lang, "lang", "l", "both", "Language for solution template (go, python, both)")
	return cmd
}

// initCmd initializes a year's structure
func initCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "init [year]",
		Short: "Initialize year structure",
		Long:  "Create the directory structure for an entire year",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			year := aoc.CurrentYear()
			if len(args) > 0 {
				var err error
				year, err = strconv.Atoi(args[0])
				if err != nil {
					return fmt.Errorf("invalid year: %s", args[0])
				}
			}

			dir := rootDir
			if dir == "" {
				dir = "."
			}
			yearDir := filepath.Join(dir, "solutions", fmt.Sprintf("%d", year))

			if err := os.MkdirAll(yearDir, 0o755); err != nil {
				return err
			}

			fmt.Printf("Initialized year %d in %s\n", year, yearDir)
			return nil
		},
	}
	return cmd
}

// setupDay sets up a day's puzzle: templates, input, and puzzle description
func setupDay(year, day int, lang string) error {
	dayDir := getDayDir(year, day)

	// Create directory
	if err := os.MkdirAll(dayDir, 0o755); err != nil {
		return err
	}

	// Create __init__.py for Python package structure
	initPath := filepath.Join(dayDir, "__init__.py")
	if _, err := os.Stat(initPath); os.IsNotExist(err) {
		if err := os.WriteFile(initPath, []byte(""), 0o644); err != nil {
			return err
		}
	}

	// Create empty answers.json
	answersPath := filepath.Join(dayDir, "answers.json")
	if _, err := os.Stat(answersPath); os.IsNotExist(err) {
		if err := os.WriteFile(answersPath, []byte("{}\n"), 0o644); err != nil {
			return err
		}
	}

	// Generate day BUILD file
	if err := generateDayBuild(dayDir, year, day); err != nil {
		return fmt.Errorf("failed to generate day BUILD: %w", err)
	}

	// Create templates
	switch lang {
	case "go":
		if err := createGoTemplate(dayDir, year, day); err != nil {
			return err
		}
	case "python", "py":
		if err := createPythonTemplate(dayDir, year, day); err != nil {
			return err
		}
	case "both":
		if err := createGoTemplate(dayDir, year, day); err != nil {
			return err
		}
		if err := createPythonTemplate(dayDir, year, day); err != nil {
			return err
		}
	}

	// Generate test files
	if err := generateTests(dayDir, year, day); err != nil {
		return fmt.Errorf("failed to generate tests: %w", err)
	}

	fmt.Printf("Created solution template in %s\n", dayDir)

	// Download input and puzzle if available
	if aoc.IsPuzzleAvailable(year, day) {
		session, err := getSession()
		if err != nil {
			fmt.Printf("Warning: %v\n", err)
		} else {
			client := aoc.NewClient(session)

			// Download input
			input, err := client.GetInput(year, day)
			if err != nil {
				fmt.Printf("Warning: could not download input: %v\n", err)
			} else {
				inputPath := filepath.Join(dayDir, "input.txt")
				os.WriteFile(inputPath, []byte(input), 0o644)
				fmt.Printf("Downloaded input to %s\n", inputPath)
			}

			// Download puzzle description
			markdown, err := client.GetPuzzleMarkdown(year, day)
			if err != nil {
				fmt.Printf("Warning: could not download puzzle: %v\n", err)
			} else {
				puzzlePath := filepath.Join(dayDir, "puzzle.md")
				os.WriteFile(puzzlePath, []byte(markdown), 0o644)
				fmt.Printf("Downloaded puzzle to %s\n", puzzlePath)
			}
		}
	}

	fmt.Printf("\nReady to solve %d Day %d!\n", year, day)
	fmt.Printf("Puzzle: https://adventofcode.com/%d/day/%d\n", year, day)
	return nil
}

func parseYearDay(args []string) (int, int, error) {
	year := aoc.CurrentYear()
	day := aoc.CurrentDay()

	if len(args) >= 1 {
		var err error
		year, err = strconv.Atoi(args[0])
		if err != nil {
			return 0, 0, fmt.Errorf("invalid year: %s", args[0])
		}
	}

	if len(args) >= 2 {
		var err error
		day, err = strconv.Atoi(args[1])
		if err != nil {
			return 0, 0, fmt.Errorf("invalid day: %s", args[1])
		}
	}

	if day == 0 {
		return 0, 0, fmt.Errorf("day not specified and not currently December 1-25")
	}

	if day < 1 || day > 25 {
		return 0, 0, fmt.Errorf("day must be between 1 and 25")
	}

	return year, day, nil
}

func createGoTemplate(dayDir string, year, day int) error {
	goDir := filepath.Join(dayDir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		return err
	}

	// Generate BUILD file
	if err := generateGoBuild(dayDir, year, day); err != nil {
		return fmt.Errorf("failed to generate go BUILD: %w", err)
	}

	goPath := filepath.Join(goDir, "solution.go")
	if _, err := os.Stat(goPath); err == nil {
		return nil // File exists, don't overwrite
	}

	// Data path for Bazel runfiles (relative to workspace root)
	dataPath := fmt.Sprintf("advent_of_code/solutions/year%d/day%02d", year, day)

	template := fmt.Sprintf(`package main

import (
	"fmt"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

func main() {
	input, err := aoc.ReadFile("%s/input.txt")
	if err != nil {
		panic(err)
	}

	fmt.Println("Part 1:", part1(input))
	fmt.Println("Part 2:", part2(input))
}

func part1(input string) int {
	lines := aoc.Lines(input)
	_ = lines
	// TODO: implement
	return 0
}

func part2(input string) int {
	lines := aoc.Lines(input)
	_ = lines
	// TODO: implement
	return 0
}
`, dataPath)

	return os.WriteFile(goPath, []byte(template), 0o644)
}

func createPythonTemplate(dayDir string, year, day int) error {
	pyDir := filepath.Join(dayDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		return err
	}

	// Create __init__.py for the python package
	initPath := filepath.Join(pyDir, "__init__.py")
	if _, err := os.Stat(initPath); os.IsNotExist(err) {
		if err := os.WriteFile(initPath, []byte(""), 0o644); err != nil {
			return err
		}
	}

	// Generate BUILD file
	if err := generatePythonBuild(dayDir, year, day); err != nil {
		return fmt.Errorf("failed to generate python BUILD: %w", err)
	}

	pyPath := filepath.Join(pyDir, "solution.py")
	if _, err := os.Stat(pyPath); err == nil {
		return nil // File exists, don't overwrite
	}

	// Data path for Bazel runfiles (relative to workspace root)
	dataPath := fmt.Sprintf("advent_of_code/solutions/year%d/day%02d", year, day)

	template := fmt.Sprintf(`#!/usr/bin/env python3
"""Advent of Code %d Day %d"""

from advent_of_code.python.aoc import lines, ints, read_file


def part1(input_text: str) -> int:
    data = lines(input_text)
    # TODO: implement
    return 0


def part2(input_text: str) -> int:
    data = lines(input_text)
    # TODO: implement
    return 0


if __name__ == "__main__":
    input_text = read_file("%s/input.txt")

    print(f"Part 1: {part1(input_text)}")
    print(f"Part 2: {part2(input_text)}")
`, year, day, dataPath)

	return os.WriteFile(pyPath, []byte(template), 0o644)
}

// generateGoTest creates or updates solution_test.go with the verified answer
func generateGoTest(dayDir string, year, day int) error {
	goDir := filepath.Join(dayDir, "go")
	testPath := filepath.Join(goDir, "solution_test.go")

	// Data path for Bazel runfiles (relative to workspace root)
	dataPath := fmt.Sprintf("advent_of_code/solutions/year%d/day%02d", year, day)

	template := fmt.Sprintf(`package main

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

type Answers struct {
	Part1 *string `+"`json:\"part1,omitempty\"`"+`
	Part2 *string `+"`json:\"part2,omitempty\"`"+`
}

func loadAnswers(t *testing.T) *Answers {
	data, err := os.ReadFile("%s/answers.json")
	if err != nil {
		t.Skipf("answers.json not found: %%v", err)
	}
	var answers Answers
	if err := json.Unmarshal(data, &answers); err != nil {
		t.Fatalf("failed to parse answers.json: %%v", err)
	}
	return &answers
}

func TestPart1(t *testing.T) {
	answers := loadAnswers(t)
	if answers.Part1 == nil {
		t.Skip("part1 answer not yet verified")
	}

	input, err := aoc.ReadFile("%s/input.txt")
	if err != nil {
		t.Fatalf("failed to read input: %%v", err)
	}

	got := part1(input)
	want := aoc.MustInt(*answers.Part1)
	if got != want {
		t.Errorf("part1() = %%d, want %%d", got, want)
	}
}

func TestPart2(t *testing.T) {
	answers := loadAnswers(t)
	if answers.Part2 == nil {
		t.Skip("part2 answer not yet verified")
	}

	input, err := aoc.ReadFile("%s/input.txt")
	if err != nil {
		t.Fatalf("failed to read input: %%v", err)
	}

	got := part2(input)
	want := aoc.MustInt(*answers.Part2)
	if got != want {
		t.Errorf("part2() = %%d, want %%d", got, want)
	}
}
`, dataPath, dataPath, dataPath)

	return os.WriteFile(testPath, []byte(template), 0o644)
}

// generatePythonTest creates or updates solution_test.py with the verified answer
func generatePythonTest(dayDir string, year, day int) error {
	pyDir := filepath.Join(dayDir, "python")
	testPath := filepath.Join(pyDir, "solution_test.py")

	// Data path for Bazel runfiles (relative to workspace root)
	dataPath := fmt.Sprintf("advent_of_code/solutions/year%d/day%02d", year, day)

	template := fmt.Sprintf(`#!/usr/bin/env python3
"""Tests for Advent of Code %d Day %d"""

import json
from pathlib import Path

import pytest

from advent_of_code.solutions.year%d.day%02d.python.solution import part1, part2


@pytest.fixture
def input_text():
    return Path("%s/input.txt").read_text()


@pytest.fixture
def answers():
    answers_path = Path("%s/answers.json")
    if not answers_path.exists():
        pytest.skip("answers.json not found")
    return json.loads(answers_path.read_text())


def test_part1(input_text, answers):
    if "part1" not in answers or answers["part1"] is None:
        pytest.skip("part1 answer not yet verified")

    got = part1(input_text)
    want = int(answers["part1"])
    assert got == want, f"part1() = {got}, want {want}"


def test_part2(input_text, answers):
    if "part2" not in answers or answers["part2"] is None:
        pytest.skip("part2 answer not yet verified")

    got = part2(input_text)
    want = int(answers["part2"])
    assert got == want, f"part2() = {got}, want {want}"
`, year, day, year, day, dataPath, dataPath)

	return os.WriteFile(testPath, []byte(template), 0o644)
}

// generateTests creates test files for both Go and Python
func generateTests(dayDir string, year, day int) error {
	// Check which solution files exist and generate corresponding tests
	goPath := filepath.Join(dayDir, "go", "solution.go")
	pyPath := filepath.Join(dayDir, "python", "solution.py")

	if _, err := os.Stat(goPath); err == nil {
		if err := generateGoTest(dayDir, year, day); err != nil {
			return fmt.Errorf("failed to generate Go test: %w", err)
		}
		fmt.Printf("Generated %s\n", filepath.Join(dayDir, "go", "solution_test.go"))
	}

	if _, err := os.Stat(pyPath); err == nil {
		// Ensure __init__.py exists in all parent directories for proper Python package
		pyDir := filepath.Join(dayDir, "python")
		if err := ensurePythonPackage(pyDir); err != nil {
			return fmt.Errorf("failed to create Python package structure: %w", err)
		}

		if err := generatePythonTest(dayDir, year, day); err != nil {
			return fmt.Errorf("failed to generate Python test: %w", err)
		}
		fmt.Printf("Generated %s\n", filepath.Join(dayDir, "python", "solution_test.py"))
	}

	return nil
}

// generateDayBuild creates the day's BUILD file with exports_files
func generateDayBuild(dayDir string, year, day int) error {
	buildPath := filepath.Join(dayDir, "BUILD")
	if _, err := os.Stat(buildPath); err == nil {
		return nil // File exists, don't overwrite
	}

	template := `load("@aspect_rules_py//py:defs.bzl", "py_library")

py_library(
    name = "day%02d",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

exports_files(
    [
        "input.txt",
        "answers.json",
    ],
    visibility = ["//:__subpackages__"],
)
`
	return os.WriteFile(buildPath, []byte(fmt.Sprintf(template, day)), 0o644)
}

// generateGoBuild creates the go/BUILD file
func generateGoBuild(dayDir string, year, day int) error {
	goDir := filepath.Join(dayDir, "go")
	buildPath := filepath.Join(goDir, "BUILD")
	if _, err := os.Stat(buildPath); err == nil {
		return nil // File exists, don't overwrite
	}

	dataPath := fmt.Sprintf("//projects/advent_of_code/solutions/year%d/day%02d", year, day)
	importPath := fmt.Sprintf("github.com/jomcgi/homelab/projects/advent_of_code/solutions/year%d/day%02d/go", year, day)

	template := `load("@rules_go//go:def.bzl", "go_binary", "go_library", "go_test")

go_library(
    name = "go_lib",
    srcs = ["solution.go"],
    importpath = "%s",
    visibility = ["//visibility:private"],
    deps = ["//projects/advent_of_code/pkg/aoc"],
)

go_binary(
    name = "go",
    data = ["%s:input.txt"],
    embed = [":go_lib"],
    visibility = ["//visibility:public"],
)

go_test(
    name = "go_test",
    srcs = ["solution_test.go"],
    data = [
        "%s:answers.json",  # keep
        "%s:input.txt",  # keep
    ],
    embed = [":go_lib"],
    deps = ["//projects/advent_of_code/pkg/aoc"],
)
`
	return os.WriteFile(buildPath, []byte(fmt.Sprintf(template, importPath, dataPath, dataPath, dataPath)), 0o644)
}

// generatePythonBuild creates the python/BUILD file
func generatePythonBuild(dayDir string, year, day int) error {
	pyDir := filepath.Join(dayDir, "python")
	buildPath := filepath.Join(pyDir, "BUILD")
	if _, err := os.Stat(buildPath); err == nil {
		return nil // File exists, don't overwrite
	}

	dataPath := fmt.Sprintf("//projects/advent_of_code/solutions/year%d/day%02d", year, day)

	template := `load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//bazel/tools/pytest:defs.bzl", "py_test")

py_binary(
    name = "solution",
    srcs = ["solution.py"],
    data = ["%s:input.txt"],
    visibility = ["//:__subpackages__"],
    deps = ["//projects/advent_of_code/python/aoc"],
)

py_library(
    name = "python",
    srcs = [
        "__init__.py",
        "solution.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = ["//projects/advent_of_code/python/aoc"],
)

py_test(
    name = "solution_test",
    srcs = ["solution_test.py"],
    data = [
        "%s:answers.json",  # keep
        "%s:input.txt",  # keep
    ],
    deps = [
        ":python",
        "@pip//pytest",
    ],
)
`
	return os.WriteFile(buildPath, []byte(fmt.Sprintf(template, dataPath, dataPath, dataPath)), 0o644)
}

// ensurePythonPackage creates __init__.py files up to advent_of_code/
func ensurePythonPackage(dayDir string) error {
	// Walk up from dayDir creating __init__.py until we hit advent_of_code
	dir := dayDir
	for {
		initPath := filepath.Join(dir, "__init__.py")
		if _, err := os.Stat(initPath); os.IsNotExist(err) {
			if err := os.WriteFile(initPath, []byte(""), 0o644); err != nil {
				return err
			}
			fmt.Printf("Generated %s\n", initPath)
		}

		// Stop when we reach advent_of_code directory
		if filepath.Base(dir) == "advent_of_code" {
			break
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			break // Reached root
		}
		dir = parent
	}
	return nil
}
