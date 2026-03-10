package main

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/jomcgi/homelab/projects/advent_of_code/pkg/aoc"
)

func main() {
	input, err := aoc.ReadFile("projects/advent_of_code/solutions/year2025/day02/input.txt")
	if err != nil {
		panic(err)
	}

	fmt.Println("Part 1:", part1(input))
	fmt.Println("Part 2:", part2(input))
}

func part1(input string) int {
	// Parse all ranges from input (comma-separated, each is start-end)
	ranges := parseRanges(input)

	sum := 0
	for _, r := range ranges {
		sum += sumInvalidInRange(r[0], r[1])
	}
	return sum
}

func parseRanges(input string) [][2]int {
	input = strings.TrimSpace(input)
	parts := strings.Split(input, ",")
	var ranges [][2]int
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		nums := aoc.Ints(p)
		if len(nums) == 2 {
			ranges = append(ranges, [2]int{nums[0], nums[1]})
		}
	}
	return ranges
}

// isInvalidID checks if a number is a "repeated twice" pattern
// e.g., 55 (5+5), 6464 (64+64), 123123 (123+123)
func isInvalidID(n int) bool {
	s := strconv.Itoa(n)
	if len(s)%2 != 0 {
		return false
	}
	half := len(s) / 2
	return s[:half] == s[half:]
}

// sumInvalidInRange finds all invalid IDs in [start, end] and returns their sum
func sumInvalidInRange(start, end int) int {
	sum := 0
	// Generate all possible "doubled" numbers and check if they're in range
	// This is more efficient than checking every number in the range
	for digits := 1; digits <= 10; digits++ {
		// Generate all doubled numbers with `digits` in each half
		minBase := 1
		if digits > 1 {
			minBase = pow10(digits - 1)
		}
		maxBase := pow10(digits) - 1

		for base := minBase; base <= maxBase; base++ {
			// Create doubled number: base repeated twice
			doubled := base*pow10(digits) + base
			if doubled >= start && doubled <= end {
				sum += doubled
			}
			if doubled > end {
				break
			}
		}
	}
	return sum
}

func pow10(n int) int {
	result := 1
	for i := 0; i < n; i++ {
		result *= 10
	}
	return result
}

func part2(input string) int {
	ranges := parseRanges(input)

	sum := 0
	for _, r := range ranges {
		sum += sumInvalidInRangeV2(r[0], r[1])
	}
	return sum
}

// isInvalidIDV2 checks if a number is a pattern repeated at least twice
// e.g., 55 (5×2), 123123 (123×2), 123123123 (123×3), 1111111 (1×7)
func isInvalidIDV2(n int) bool {
	s := strconv.Itoa(n)
	length := len(s)

	// Try all possible base lengths that divide the total length
	// and result in at least 2 repetitions
	for baseLen := 1; baseLen <= length/2; baseLen++ {
		if length%baseLen != 0 {
			continue
		}
		reps := length / baseLen
		if reps < 2 {
			continue
		}

		base := s[:baseLen]
		valid := true
		for i := 1; i < reps; i++ {
			if s[i*baseLen:(i+1)*baseLen] != base {
				valid = false
				break
			}
		}
		if valid {
			return true
		}
	}
	return false
}

// sumInvalidInRangeV2 finds all invalid IDs (repeated at least twice) in [start, end]
func sumInvalidInRangeV2(start, end int) int {
	seen := make(map[int]bool)

	// Calculate the multiplier for a given base length and reps
	// e.g., for baseDigits=2, reps=3: multiplier = 1 + 100 + 10000 = 10101
	getMultiplier := func(baseDigits, reps int) int {
		mult := 0
		p := 1
		for r := 0; r < reps; r++ {
			mult += p
			p *= pow10(baseDigits)
		}
		return mult
	}

	// For each base length
	for baseDigits := 1; baseDigits <= 10; baseDigits++ {
		minBase := 1
		if baseDigits > 1 {
			minBase = pow10(baseDigits - 1)
		}
		maxBase := pow10(baseDigits) - 1

		// Try different repetition counts (at least 2)
		for reps := 2; reps <= 20; reps++ {
			multiplier := getMultiplier(baseDigits, reps)

			// Check if any number in this category could be in range
			minNum := minBase * multiplier
			maxNum := maxBase * multiplier

			if minNum > end {
				break // All larger reps will also be too big
			}
			if maxNum < start {
				continue // This category is entirely below range
			}

			// Calculate the range of bases that produce numbers in [start, end]
			loBase := (start + multiplier - 1) / multiplier // ceiling division
			if loBase < minBase {
				loBase = minBase
			}
			hiBase := end / multiplier
			if hiBase > maxBase {
				hiBase = maxBase
			}

			for base := loBase; base <= hiBase; base++ {
				num := base * multiplier
				if num >= start && num <= end && !seen[num] {
					seen[num] = true
				}
			}
		}
	}

	sum := 0
	for num := range seen {
		sum += num
	}
	return sum
}
