package main

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

type Answers struct {
	Part1 *string `json:"part1,omitempty"`
	Part2 *string `json:"part2,omitempty"`
}

func loadAnswers(t *testing.T) *Answers {
	data, err := os.ReadFile("projects/advent_of_code/solutions/year2015/day04/answers.json")
	if err != nil {
		t.Skipf("answers.json not found: %v", err)
	}
	var answers Answers
	if err := json.Unmarshal(data, &answers); err != nil {
		t.Fatalf("failed to parse answers.json: %v", err)
	}
	return &answers
}

func TestPart1(t *testing.T) {
	answers := loadAnswers(t)
	if answers.Part1 == nil {
		t.Skip("part1 answer not yet verified")
	}

	input, err := aoc.ReadFile("projects/advent_of_code/solutions/year2015/day04/input.txt")
	if err != nil {
		t.Fatalf("failed to read input: %v", err)
	}

	got := part1(input)
	want := aoc.MustInt(*answers.Part1)
	if got != want {
		t.Errorf("part1() = %d, want %d", got, want)
	}
}

func TestPart2(t *testing.T) {
	answers := loadAnswers(t)
	if answers.Part2 == nil {
		t.Skip("part2 answer not yet verified")
	}

	input, err := aoc.ReadFile("projects/advent_of_code/solutions/year2015/day04/input.txt")
	if err != nil {
		t.Fatalf("failed to read input: %v", err)
	}

	got := part2(input)
	want := aoc.MustInt(*answers.Part2)
	if got != want {
		t.Errorf("part2() = %d, want %d", got, want)
	}
}
