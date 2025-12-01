package aoc

import (
	"bufio"
	"os"
	"strconv"
	"strings"
)

func ReadFile(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return strings.TrimRight(string(data), "\n"), nil
}

func ReadLines(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var lines []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	return lines, scanner.Err()
}

func Lines(s string) []string {
	s = strings.TrimRight(s, "\n")
	if s == "" {
		return nil
	}
	return strings.Split(s, "\n")
}

// Paragraphs splits input by blank lines (double newlines)
func Paragraphs(s string) []string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	return strings.Split(s, "\n\n")
}

// Ints extracts all integers from a string
func Ints(s string) []int {
	var result []int
	var current strings.Builder
	negative := false

	for i, r := range s {
		if r == '-' {
			// Check if this could be a negative sign
			if current.Len() == 0 {
				// Look ahead to see if followed by digit
				if i+1 < len(s) && s[i+1] >= '0' && s[i+1] <= '9' {
					negative = true
					continue
				}
			}
		}
		if r >= '0' && r <= '9' {
			current.WriteRune(r)
		} else if current.Len() > 0 {
			n, _ := strconv.Atoi(current.String())
			if negative {
				n = -n
			}
			result = append(result, n)
			current.Reset()
			negative = false
		} else {
			negative = false
		}
	}

	if current.Len() > 0 {
		n, _ := strconv.Atoi(current.String())
		if negative {
			n = -n
		}
		result = append(result, n)
	}

	return result
}

// MustInt converts a string to int, panics on error
func MustInt(s string) int {
	n, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil {
		panic(err)
	}
	return n
}

func MustInts(ss []string) []int {
	result := make([]int, len(ss))
	for i, s := range ss {
		result[i] = MustInt(s)
	}
	return result
}

func Fields(s string) []string {
	return strings.Fields(s)
}

// Split splits by separator and trims each part
func Split(s, sep string) []string {
	parts := strings.Split(s, sep)
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			result = append(result, p)
		}
	}
	return result
}

func Chars(s string) []string {
	result := make([]string, len(s))
	for i, r := range s {
		result[i] = string(r)
	}
	return result
}

func Runes(s string) []rune {
	return []rune(s)
}
