package main

import (
	"fmt"
	"strings"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

func main() {
	input, err := aoc.ReadFile("../input.txt")
	if err != nil {
		panic(err)
	}

	fmt.Println("Part 1:", part1(input))
	fmt.Println("Part 2:", part2(input))
}

func part1(input string) int {
	directions := map[rune]aoc.Point{
		'^': aoc.Up,
		'v': aoc.Down,
		'<': aoc.Left,
		'>': aoc.Right,
	}

	visited := map[aoc.Point]bool{{X: 0, Y: 0}: true}
	pos := aoc.Point{X: 0, Y: 0}

	for _, char := range strings.TrimSpace(input) {
		pos = pos.Add(directions[char])
		visited[pos] = true
	}

	return len(visited)
}

func part2(input string) int {
	directions := map[rune]aoc.Point{
		'^': aoc.Up,
		'v': aoc.Down,
		'<': aoc.Left,
		'>': aoc.Right,
	}

	visited := map[aoc.Point]bool{{X: 0, Y: 0}: true}
	santaPos := aoc.Point{X: 0, Y: 0}
	roboPos := aoc.Point{X: 0, Y: 0}

	for i, char := range strings.TrimSpace(input) {
		if i%2 == 0 {
			santaPos = santaPos.Add(directions[char])
			visited[santaPos] = true
		} else {
			roboPos = roboPos.Add(directions[char])
			visited[roboPos] = true
		}
	}

	return len(visited)
}
