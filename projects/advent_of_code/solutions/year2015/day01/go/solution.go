package main

import (
	"fmt"

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
	floor := 0
	for _, char := range input {
		if char == '(' {
			floor++
		} else if char == ')' {
			floor--
		}
	}
	return floor
}

func part2(input string) int {
	floor := 0
	for position, char := range input {
		if char == '(' {
			floor++
		} else if char == ')' {
			floor--
		}
		if floor == -1 {
			return position + 1
		}
	}
	return 0
}
