package main

import (
	"fmt"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

func main() {
	input, err := aoc.ReadFile("projects/advent_of_code/solutions/year2025/day03/input.txt")
	if err != nil {
		panic(err)
	}

	fmt.Println("Part 1:", part1(input))
	fmt.Println("Part 2:", part2(input))
}

func part1(input string) int {
	lines := aoc.Lines(input)
	total := 0
	for _, line := range lines {
		total += maxJoltage(line)
	}
	return total
}

func maxJoltage(line string) int {
	n := len(line)
	maxVal := 0

	for i := 0; i < n-1; i++ {
		firstDigit := int(line[i] - '0')
		// Find max digit from i+1 to end
		maxSecond := 0
		for j := i + 1; j < n; j++ {
			d := int(line[j] - '0')
			if d > maxSecond {
				maxSecond = d
			}
		}
		val := firstDigit*10 + maxSecond
		if val > maxVal {
			maxVal = val
		}
	}

	return maxVal
}

func part2(input string) int {
	lines := aoc.Lines(input)
	total := 0
	for _, line := range lines {
		total += maxJoltage12(line)
	}
	return total
}

func maxJoltage12(line string) int {
	n := len(line)
	keep := 12

	result := 0
	start := 0

	for i := 0; i < keep; i++ {
		// For digit position i, we can pick from start to n-12+i (inclusive)
		// This ensures we leave enough digits for remaining positions
		end := n - keep + i

		// Find the maximum digit in range [start, end]
		maxDigit := byte('0')
		maxIdx := start
		for j := start; j <= end; j++ {
			if line[j] > maxDigit {
				maxDigit = line[j]
				maxIdx = j
			}
		}

		result = result*10 + int(maxDigit-'0')
		start = maxIdx + 1
	}

	return result
}
