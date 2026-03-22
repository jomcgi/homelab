package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// loadAnswers / saveAnswers
// ---------------------------------------------------------------------------

func TestLoadAnswers_MissingFile(t *testing.T) {
	dir := t.TempDir()

	got, err := loadAnswers(dir)
	if err != nil {
		t.Fatalf("loadAnswers() error = %v, want nil", err)
	}
	if got.Part1 != nil || got.Part2 != nil {
		t.Errorf("loadAnswers() = %+v, want empty Answers{}", got)
	}
}

func TestLoadAnswers_HappyPath(t *testing.T) {
	dir := t.TempDir()

	p1 := "42"
	p2 := "99"
	answers := Answers{Part1: &p1, Part2: &p2}
	data, err := json.MarshalIndent(answers, "", "  ")
	if err != nil {
		t.Fatalf("json.MarshalIndent: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "answers.json"), data, 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	got, err := loadAnswers(dir)
	if err != nil {
		t.Fatalf("loadAnswers() error = %v, want nil", err)
	}
	if got.Part1 == nil || *got.Part1 != p1 {
		t.Errorf("Part1 = %v, want %q", got.Part1, p1)
	}
	if got.Part2 == nil || *got.Part2 != p2 {
		t.Errorf("Part2 = %v, want %q", got.Part2, p2)
	}
}

func TestLoadAnswers_InvalidJSON(t *testing.T) {
	dir := t.TempDir()

	if err := os.WriteFile(filepath.Join(dir, "answers.json"), []byte("not-json"), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	_, err := loadAnswers(dir)
	if err == nil {
		t.Error("loadAnswers() error = nil, want non-nil for invalid JSON")
	}
}

func TestSaveAnswers_HappyPath(t *testing.T) {
	dir := t.TempDir()

	p1 := "123"
	answers := &Answers{Part1: &p1}
	if err := saveAnswers(dir, answers); err != nil {
		t.Fatalf("saveAnswers() error = %v, want nil", err)
	}

	data, err := os.ReadFile(filepath.Join(dir, "answers.json"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}

	var got Answers
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	if got.Part1 == nil || *got.Part1 != p1 {
		t.Errorf("Part1 = %v, want %q", got.Part1, p1)
	}
}

func TestSaveAnswers_RoundTrip(t *testing.T) {
	dir := t.TempDir()

	p1 := "100"
	p2 := "200"
	original := &Answers{Part1: &p1, Part2: &p2}

	if err := saveAnswers(dir, original); err != nil {
		t.Fatalf("saveAnswers() error = %v", err)
	}

	got, err := loadAnswers(dir)
	if err != nil {
		t.Fatalf("loadAnswers() error = %v", err)
	}

	if got.Part1 == nil || *got.Part1 != p1 {
		t.Errorf("Part1 = %v, want %q", got.Part1, p1)
	}
	if got.Part2 == nil || *got.Part2 != p2 {
		t.Errorf("Part2 = %v, want %q", got.Part2, p2)
	}
}

// ---------------------------------------------------------------------------
// getDayDir
// ---------------------------------------------------------------------------

func TestGetDayDir_FormatsDay(t *testing.T) {
	orig := rootDir
	t.Cleanup(func() { rootDir = orig })
	rootDir = "/base"

	tests := []struct {
		year    int
		day     int
		wantSub string
	}{
		{2024, 1, "day01"},
		{2024, 9, "day09"},
		{2024, 10, "day10"},
		{2024, 25, "day25"},
	}

	for _, tc := range tests {
		got := getDayDir(tc.year, tc.day)
		if !strings.Contains(got, tc.wantSub) {
			t.Errorf("getDayDir(%d, %d) = %q, want to contain %q", tc.year, tc.day, got, tc.wantSub)
		}
	}
}

func TestGetDayDir_FormatsYear(t *testing.T) {
	orig := rootDir
	t.Cleanup(func() { rootDir = orig })
	rootDir = "/base"

	got := getDayDir(2025, 3)
	if !strings.Contains(got, "year2025") {
		t.Errorf("getDayDir(2025, 3) = %q, want to contain %q", got, "year2025")
	}
}

func TestGetDayDir_DefaultRootDir(t *testing.T) {
	orig := rootDir
	t.Cleanup(func() { rootDir = orig })
	rootDir = ""

	got := getDayDir(2024, 5)
	if !strings.HasPrefix(got, "advent_of_code") {
		t.Errorf("getDayDir with empty rootDir = %q, want prefix %q", got, "advent_of_code")
	}
}

func TestGetDayDir_CustomRootDir(t *testing.T) {
	orig := rootDir
	t.Cleanup(func() { rootDir = orig })
	rootDir = "/custom/path"

	got := getDayDir(2024, 5)
	if !strings.HasPrefix(got, "/custom/path") {
		t.Errorf("getDayDir with custom rootDir = %q, want prefix %q", got, "/custom/path")
	}
}

// ---------------------------------------------------------------------------
// parseYearDay
// ---------------------------------------------------------------------------

func TestParseYearDay_InvalidYear(t *testing.T) {
	_, _, err := parseYearDay([]string{"not-a-year"})
	if err == nil {
		t.Error("parseYearDay(invalid year) error = nil, want non-nil")
	}
}

func TestParseYearDay_InvalidDay(t *testing.T) {
	_, _, err := parseYearDay([]string{"2024", "not-a-day"})
	if err == nil {
		t.Error("parseYearDay(invalid day) error = nil, want non-nil")
	}
}

func TestParseYearDay_DayZeroError(t *testing.T) {
	// Day 0 should produce an error
	_, _, err := parseYearDay([]string{"2024", "0"})
	if err == nil {
		t.Error("parseYearDay(day=0) error = nil, want non-nil")
	}
}

func TestParseYearDay_DayTooLarge(t *testing.T) {
	_, _, err := parseYearDay([]string{"2024", "26"})
	if err == nil {
		t.Error("parseYearDay(day=26) error = nil, want non-nil")
	}
}

func TestParseYearDay_Day25Valid(t *testing.T) {
	year, day, err := parseYearDay([]string{"2024", "25"})
	if err != nil {
		t.Fatalf("parseYearDay(2024, 25) error = %v, want nil", err)
	}
	if year != 2024 {
		t.Errorf("year = %d, want 2024", year)
	}
	if day != 25 {
		t.Errorf("day = %d, want 25", day)
	}
}

func TestParseYearDay_Day1Valid(t *testing.T) {
	year, day, err := parseYearDay([]string{"2024", "1"})
	if err != nil {
		t.Fatalf("parseYearDay(2024, 1) error = %v, want nil", err)
	}
	if year != 2024 {
		t.Errorf("year = %d, want 2024", year)
	}
	if day != 1 {
		t.Errorf("day = %d, want 1", day)
	}
}

func TestParseYearDay_ExplicitYearAndDay(t *testing.T) {
	year, day, err := parseYearDay([]string{"2015", "12"})
	if err != nil {
		t.Fatalf("parseYearDay() error = %v", err)
	}
	if year != 2015 {
		t.Errorf("year = %d, want 2015", year)
	}
	if day != 12 {
		t.Errorf("day = %d, want 12", day)
	}
}

// ---------------------------------------------------------------------------
// createGoTemplate
// ---------------------------------------------------------------------------

func TestCreateGoTemplate_CreatesFile(t *testing.T) {
	dir := t.TempDir()

	orig := rootDir
	t.Cleanup(func() { rootDir = orig })
	rootDir = dir

	dayDir := filepath.Join(dir, "day01")
	if err := os.MkdirAll(dayDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := createGoTemplate(dayDir, 2024, 1); err != nil {
		t.Fatalf("createGoTemplate() error = %v", err)
	}

	goPath := filepath.Join(dayDir, "go", "solution.go")
	if _, err := os.Stat(goPath); err != nil {
		t.Errorf("solution.go not created: %v", err)
	}
}

func TestCreateGoTemplate_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	if err := os.MkdirAll(dayDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := createGoTemplate(dayDir, 2024, 1); err != nil {
		t.Fatalf("createGoTemplate() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(dayDir, "go", "solution.go"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{"package main", "func part1", "func part2", "func main"} {
		if !strings.Contains(content, want) {
			t.Errorf("solution.go missing %q", want)
		}
	}
}

func TestCreateGoTemplate_SkipsIfFileExists(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	goDir := filepath.Join(dayDir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	// Write sentinel content to the solution file
	sentinel := "// existing file content"
	if err := os.WriteFile(filepath.Join(goDir, "solution.go"), []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := createGoTemplate(dayDir, 2024, 1); err != nil {
		t.Fatalf("createGoTemplate() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(goDir, "solution.go"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) != sentinel {
		t.Errorf("existing file was overwritten; got %q, want %q", string(data), sentinel)
	}
}

// ---------------------------------------------------------------------------
// createPythonTemplate
// ---------------------------------------------------------------------------

func TestCreatePythonTemplate_CreatesFile(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	if err := os.MkdirAll(dayDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := createPythonTemplate(dayDir, 2024, 1); err != nil {
		t.Fatalf("createPythonTemplate() error = %v", err)
	}

	pyPath := filepath.Join(dayDir, "python", "solution.py")
	if _, err := os.Stat(pyPath); err != nil {
		t.Errorf("solution.py not created: %v", err)
	}
}

func TestCreatePythonTemplate_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	if err := os.MkdirAll(dayDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := createPythonTemplate(dayDir, 2024, 1); err != nil {
		t.Fatalf("createPythonTemplate() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(dayDir, "python", "solution.py"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{"def part1", "def part2", "Advent of Code 2024", "Day 1"} {
		if !strings.Contains(content, want) {
			t.Errorf("solution.py missing %q", want)
		}
	}
}

func TestCreatePythonTemplate_SkipsIfFileExists(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	pyDir := filepath.Join(dayDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	sentinel := "# existing python file"
	if err := os.WriteFile(filepath.Join(pyDir, "solution.py"), []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := createPythonTemplate(dayDir, 2024, 1); err != nil {
		t.Fatalf("createPythonTemplate() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(pyDir, "solution.py"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) != sentinel {
		t.Errorf("existing file was overwritten; got %q, want %q", string(data), sentinel)
	}
}

// ---------------------------------------------------------------------------
// generateDayBuild
// ---------------------------------------------------------------------------

func TestGenerateDayBuild_CreatesFile(t *testing.T) {
	dir := t.TempDir()

	if err := generateDayBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generateDayBuild() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(dir, "BUILD")); err != nil {
		t.Errorf("BUILD not created: %v", err)
	}
}

func TestGenerateDayBuild_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()

	if err := generateDayBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generateDayBuild() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(dir, "BUILD"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{"exports_files", "input.txt", "answers.json"} {
		if !strings.Contains(content, want) {
			t.Errorf("BUILD missing %q", want)
		}
	}
}

func TestGenerateDayBuild_SkipsIfFileExists(t *testing.T) {
	dir := t.TempDir()

	sentinel := "# existing BUILD content"
	if err := os.WriteFile(filepath.Join(dir, "BUILD"), []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := generateDayBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generateDayBuild() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(dir, "BUILD"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) != sentinel {
		t.Errorf("existing BUILD was overwritten; got %q, want %q", string(data), sentinel)
	}
}

// ---------------------------------------------------------------------------
// generateGoBuild
// ---------------------------------------------------------------------------

func TestGenerateGoBuild_CreatesFile(t *testing.T) {
	dir := t.TempDir()
	goDir := filepath.Join(dir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generateGoBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generateGoBuild() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(goDir, "BUILD")); err != nil {
		t.Errorf("go/BUILD not created: %v", err)
	}
}

func TestGenerateGoBuild_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()
	goDir := filepath.Join(dir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generateGoBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generateGoBuild() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(goDir, "BUILD"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{"go_binary", "go_library", "go_test", "solution.go", "solution_test.go"} {
		if !strings.Contains(content, want) {
			t.Errorf("go/BUILD missing %q", want)
		}
	}
}

func TestGenerateGoBuild_SkipsIfFileExists(t *testing.T) {
	dir := t.TempDir()
	goDir := filepath.Join(dir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	sentinel := "# existing go BUILD"
	if err := os.WriteFile(filepath.Join(goDir, "BUILD"), []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := generateGoBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generateGoBuild() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(goDir, "BUILD"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) != sentinel {
		t.Errorf("existing go/BUILD was overwritten; got %q, want %q", string(data), sentinel)
	}
}

// ---------------------------------------------------------------------------
// generatePythonBuild
// ---------------------------------------------------------------------------

func TestGeneratePythonBuild_CreatesFile(t *testing.T) {
	dir := t.TempDir()
	pyDir := filepath.Join(dir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generatePythonBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generatePythonBuild() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(pyDir, "BUILD")); err != nil {
		t.Errorf("python/BUILD not created: %v", err)
	}
}

func TestGeneratePythonBuild_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()
	pyDir := filepath.Join(dir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generatePythonBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generatePythonBuild() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(pyDir, "BUILD"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{"py_binary", "py_library", "py_test", "solution.py", "solution_test.py"} {
		if !strings.Contains(content, want) {
			t.Errorf("python/BUILD missing %q", want)
		}
	}
}

func TestGeneratePythonBuild_SkipsIfFileExists(t *testing.T) {
	dir := t.TempDir()
	pyDir := filepath.Join(dir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	sentinel := "# existing python BUILD"
	if err := os.WriteFile(filepath.Join(pyDir, "BUILD"), []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := generatePythonBuild(dir, 2024, 1); err != nil {
		t.Fatalf("generatePythonBuild() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(pyDir, "BUILD"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) != sentinel {
		t.Errorf("existing python/BUILD was overwritten; got %q, want %q", string(data), sentinel)
	}
}

// ---------------------------------------------------------------------------
// ensurePythonPackage
// ---------------------------------------------------------------------------

func TestEnsurePythonPackage_CreatesInitPy(t *testing.T) {
	// Build a directory tree: tmpdir/advent_of_code/solutions/year2024/day01/python
	base := t.TempDir()
	aocDir := filepath.Join(base, "advent_of_code")
	pyDir := filepath.Join(aocDir, "solutions", "year2024", "day01", "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := ensurePythonPackage(pyDir); err != nil {
		t.Fatalf("ensurePythonPackage() error = %v", err)
	}

	// __init__.py should exist at every level up to and including advent_of_code
	for _, dir := range []string{
		pyDir,
		filepath.Join(aocDir, "solutions", "year2024", "day01"),
		filepath.Join(aocDir, "solutions", "year2024"),
		filepath.Join(aocDir, "solutions"),
		aocDir,
	} {
		initPath := filepath.Join(dir, "__init__.py")
		if _, err := os.Stat(initPath); err != nil {
			t.Errorf("__init__.py not created at %s: %v", dir, err)
		}
	}
}

func TestEnsurePythonPackage_StopsAtAdventOfCode(t *testing.T) {
	// Verify it does NOT create __init__.py above advent_of_code
	base := t.TempDir()
	aocDir := filepath.Join(base, "advent_of_code")
	pyDir := filepath.Join(aocDir, "solutions", "day01", "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := ensurePythonPackage(pyDir); err != nil {
		t.Fatalf("ensurePythonPackage() error = %v", err)
	}

	// base (parent of advent_of_code) must NOT have __init__.py
	abovePath := filepath.Join(base, "__init__.py")
	if _, err := os.Stat(abovePath); err == nil {
		t.Errorf("__init__.py was created above advent_of_code at %s", abovePath)
	}
}

func TestEnsurePythonPackage_DoesNotOverwriteExisting(t *testing.T) {
	base := t.TempDir()
	aocDir := filepath.Join(base, "advent_of_code")
	pyDir := filepath.Join(aocDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	// Write sentinel into an existing __init__.py
	sentinel := "# pre-existing"
	if err := os.WriteFile(filepath.Join(pyDir, "__init__.py"), []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := ensurePythonPackage(pyDir); err != nil {
		t.Fatalf("ensurePythonPackage() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(pyDir, "__init__.py"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) != sentinel {
		t.Errorf("existing __init__.py was overwritten; got %q, want %q", string(data), sentinel)
	}
}

// ---------------------------------------------------------------------------
// generateGoTest
// ---------------------------------------------------------------------------

func TestGenerateGoTest_CreatesFile(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	goDir := filepath.Join(dayDir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generateGoTest(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateGoTest() error = %v", err)
	}

	testPath := filepath.Join(goDir, "solution_test.go")
	if _, err := os.Stat(testPath); err != nil {
		t.Errorf("solution_test.go not created: %v", err)
	}
}

func TestGenerateGoTest_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	goDir := filepath.Join(dayDir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generateGoTest(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateGoTest() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(goDir, "solution_test.go"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{"TestPart1", "TestPart2", "answers.json", "input.txt", "year2024/day01"} {
		if !strings.Contains(content, want) {
			t.Errorf("solution_test.go missing %q", want)
		}
	}
}

func TestGenerateGoTest_OverwritesExistingFile(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	goDir := filepath.Join(dayDir, "go")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	// Write sentinel content into the file first
	sentinel := "// old content"
	testPath := filepath.Join(goDir, "solution_test.go")
	if err := os.WriteFile(testPath, []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := generateGoTest(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateGoTest() error = %v", err)
	}

	data, err := os.ReadFile(testPath)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) == sentinel {
		t.Error("generateGoTest() left existing file unchanged; expected an overwrite")
	}
}

func TestGenerateGoTest_DataPathContainsYearAndDay(t *testing.T) {
	tests := []struct {
		year     int
		day      int
		wantYear string
		wantDay  string
	}{
		{2015, 1, "year2015", "day01"},
		{2024, 25, "year2024", "day25"},
		{2023, 9, "year2023", "day09"},
	}

	for _, tc := range tests {
		t.Run(fmt.Sprintf("%d_day%d", tc.year, tc.day), func(t *testing.T) {
			dir := t.TempDir()
			dayDir := filepath.Join(dir, "dayXX")
			goDir := filepath.Join(dayDir, "go")
			if err := os.MkdirAll(goDir, 0o755); err != nil {
				t.Fatalf("MkdirAll: %v", err)
			}

			if err := generateGoTest(dayDir, tc.year, tc.day); err != nil {
				t.Fatalf("generateGoTest() error = %v", err)
			}

			data, err := os.ReadFile(filepath.Join(goDir, "solution_test.go"))
			if err != nil {
				t.Fatalf("ReadFile: %v", err)
			}
			content := string(data)

			if !strings.Contains(content, tc.wantYear) {
				t.Errorf("solution_test.go missing year %q", tc.wantYear)
			}
			if !strings.Contains(content, tc.wantDay) {
				t.Errorf("solution_test.go missing day %q", tc.wantDay)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// generatePythonTest
// ---------------------------------------------------------------------------

func TestGeneratePythonTest_CreatesFile(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	pyDir := filepath.Join(dayDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generatePythonTest(dayDir, 2024, 1); err != nil {
		t.Fatalf("generatePythonTest() error = %v", err)
	}

	testPath := filepath.Join(pyDir, "solution_test.py")
	if _, err := os.Stat(testPath); err != nil {
		t.Errorf("solution_test.py not created: %v", err)
	}
}

func TestGeneratePythonTest_ContentHasExpectedStrings(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	pyDir := filepath.Join(dayDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generatePythonTest(dayDir, 2024, 1); err != nil {
		t.Fatalf("generatePythonTest() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(pyDir, "solution_test.py"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	for _, want := range []string{
		"test_part1",
		"test_part2",
		"@pytest.fixture",
		"import pytest",
		"answers.json",
		"input.txt",
		"year2024",
		"day01",
	} {
		if !strings.Contains(content, want) {
			t.Errorf("solution_test.py missing %q", want)
		}
	}
}

func TestGeneratePythonTest_ImportPathContainsYearAndDay(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "dayXX")
	pyDir := filepath.Join(dayDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	if err := generatePythonTest(dayDir, 2024, 5); err != nil {
		t.Fatalf("generatePythonTest() error = %v", err)
	}

	data, err := os.ReadFile(filepath.Join(pyDir, "solution_test.py"))
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	content := string(data)

	// Import path should reference the correct module
	for _, want := range []string{"year2024", "day05", "part1", "part2"} {
		if !strings.Contains(content, want) {
			t.Errorf("solution_test.py import path missing %q", want)
		}
	}
}

func TestGeneratePythonTest_OverwritesExistingFile(t *testing.T) {
	dir := t.TempDir()
	dayDir := filepath.Join(dir, "day01")
	pyDir := filepath.Join(dayDir, "python")
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	// Write sentinel content into the file first
	sentinel := "# old python test content"
	testPath := filepath.Join(pyDir, "solution_test.py")
	if err := os.WriteFile(testPath, []byte(sentinel), 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if err := generatePythonTest(dayDir, 2024, 1); err != nil {
		t.Fatalf("generatePythonTest() error = %v", err)
	}

	data, err := os.ReadFile(testPath)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(data) == sentinel {
		t.Error("generatePythonTest() left existing file unchanged; expected an overwrite")
	}
}

// ---------------------------------------------------------------------------
// generateTests
// ---------------------------------------------------------------------------

// makeAocDayDir returns a dayDir rooted inside an "advent_of_code" directory so
// that ensurePythonPackage (called by generateTests) stops walking at the right
// level and does not attempt to create __init__.py in system directories.
func makeAocDayDir(t *testing.T) (dayDir, goDir, pyDir string) {
	t.Helper()
	base := t.TempDir()
	dayDir = filepath.Join(base, "advent_of_code", "solutions", "year2024", "day01")
	goDir = filepath.Join(dayDir, "go")
	pyDir = filepath.Join(dayDir, "python")
	if err := os.MkdirAll(goDir, 0o755); err != nil {
		t.Fatalf("MkdirAll(goDir): %v", err)
	}
	if err := os.MkdirAll(pyDir, 0o755); err != nil {
		t.Fatalf("MkdirAll(pyDir): %v", err)
	}
	return dayDir, goDir, pyDir
}

func TestGenerateTests_BothSolutionsExist(t *testing.T) {
	dayDir, goDir, pyDir := makeAocDayDir(t)

	if err := os.WriteFile(filepath.Join(goDir, "solution.go"), []byte("package main"), 0o644); err != nil {
		t.Fatalf("WriteFile solution.go: %v", err)
	}
	if err := os.WriteFile(filepath.Join(pyDir, "solution.py"), []byte("# solution"), 0o644); err != nil {
		t.Fatalf("WriteFile solution.py: %v", err)
	}

	if err := generateTests(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateTests() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(goDir, "solution_test.go")); err != nil {
		t.Errorf("solution_test.go not created: %v", err)
	}
	if _, err := os.Stat(filepath.Join(pyDir, "solution_test.py")); err != nil {
		t.Errorf("solution_test.py not created: %v", err)
	}
}

func TestGenerateTests_OnlyGoSolutionExists(t *testing.T) {
	dayDir, goDir, pyDir := makeAocDayDir(t)

	if err := os.WriteFile(filepath.Join(goDir, "solution.go"), []byte("package main"), 0o644); err != nil {
		t.Fatalf("WriteFile solution.go: %v", err)
	}
	// No solution.py

	if err := generateTests(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateTests() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(goDir, "solution_test.go")); err != nil {
		t.Errorf("solution_test.go not created: %v", err)
	}
	if _, err := os.Stat(filepath.Join(pyDir, "solution_test.py")); err == nil {
		t.Error("solution_test.py was created but should not have been (no solution.py)")
	}
}

func TestGenerateTests_OnlyPythonSolutionExists(t *testing.T) {
	dayDir, goDir, pyDir := makeAocDayDir(t)

	// No solution.go
	if err := os.WriteFile(filepath.Join(pyDir, "solution.py"), []byte("# solution"), 0o644); err != nil {
		t.Fatalf("WriteFile solution.py: %v", err)
	}

	if err := generateTests(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateTests() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(goDir, "solution_test.go")); err == nil {
		t.Error("solution_test.go was created but should not have been (no solution.go)")
	}
	if _, err := os.Stat(filepath.Join(pyDir, "solution_test.py")); err != nil {
		t.Errorf("solution_test.py not created: %v", err)
	}
}

func TestGenerateTests_NeitherSolutionExists(t *testing.T) {
	dayDir, goDir, pyDir := makeAocDayDir(t)
	// No solution files at all

	if err := generateTests(dayDir, 2024, 1); err != nil {
		t.Fatalf("generateTests() error = %v", err)
	}

	if _, err := os.Stat(filepath.Join(goDir, "solution_test.go")); err == nil {
		t.Error("solution_test.go was created but should not have been")
	}
	if _, err := os.Stat(filepath.Join(pyDir, "solution_test.py")); err == nil {
		t.Error("solution_test.py was created but should not have been")
	}
}

// ---------------------------------------------------------------------------
// getSession
// ---------------------------------------------------------------------------

func TestGetSession_UsesSessionVar(t *testing.T) {
	orig := sessionVar
	t.Cleanup(func() { sessionVar = orig })
	sessionVar = "my-test-session-token"

	got, err := getSession()
	if err != nil {
		t.Fatalf("getSession() error = %v, want nil", err)
	}
	if got != "my-test-session-token" {
		t.Errorf("getSession() = %q, want %q", got, "my-test-session-token")
	}
}

func TestGetSession_SessionVarTakesPrecedenceOverEmpty(t *testing.T) {
	orig := sessionVar
	t.Cleanup(func() { sessionVar = orig })

	// When sessionVar is non-empty, getSession must return it without error
	// regardless of the environment or cookie store.
	sessionVar = "explicit-session-abc123"

	got, err := getSession()
	if err != nil {
		t.Fatalf("getSession() with non-empty sessionVar returned error: %v", err)
	}
	if got != sessionVar {
		t.Errorf("getSession() = %q, want %q", got, sessionVar)
	}
}

func TestGetSession_EmptySessionVarFallsThrough(t *testing.T) {
	orig := sessionVar
	t.Cleanup(func() { sessionVar = orig })
	sessionVar = ""

	// With an empty sessionVar, getSession() delegates to cookies.GetSession().
	// In CI / test environments there is no browser cookie store, so an error
	// is the expected outcome. We just verify the function does not panic and
	// that it does NOT return the empty string as a valid session.
	got, err := getSession()
	if err == nil && got == "" {
		t.Error("getSession() with empty sessionVar returned empty string without error")
	}
}
