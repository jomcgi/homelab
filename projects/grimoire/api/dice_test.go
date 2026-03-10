package main

import (
	"strings"
	"testing"
)

// TestParseAndRollBasicSum tests plain NdS notation.
func TestParseAndRollBasicSum(t *testing.T) {
	for i := 0; i < 20; i++ {
		result, detail, err := parseAndRoll("2d6")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result < 2 || result > 12 {
			t.Errorf("2d6 result %d out of range [2,12]", result)
		}
		if detail == "" {
			t.Error("detail should not be empty")
		}
	}
}

// TestParseAndRollSingleDie tests a single die (d20).
func TestParseAndRollSingleDie(t *testing.T) {
	for i := 0; i < 20; i++ {
		result, _, err := parseAndRoll("1d20")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result < 1 || result > 20 {
			t.Errorf("1d20 result %d out of range [1,20]", result)
		}
	}
}

// TestParseAndRollPositiveModifier tests NdS+M notation.
func TestParseAndRollPositiveModifier(t *testing.T) {
	for i := 0; i < 20; i++ {
		result, detail, err := parseAndRoll("1d6+3")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result < 4 || result > 9 {
			t.Errorf("1d6+3 result %d out of range [4,9]", result)
		}
		if !strings.Contains(detail, "+3") {
			t.Errorf("detail %q should contain '+3'", detail)
		}
	}
}

// TestParseAndRollNegativeModifier tests NdS-M notation.
func TestParseAndRollNegativeModifier(t *testing.T) {
	for i := 0; i < 20; i++ {
		result, detail, err := parseAndRoll("1d6-2")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result < -1 || result > 4 {
			t.Errorf("1d6-2 result %d out of range [-1,4]", result)
		}
		_ = detail
	}
}

// TestParseAndRollAdvantage tests that 1d20adv result is within [1,20].
func TestParseAndRollAdvantage(t *testing.T) {
	for i := 0; i < 30; i++ {
		result, detail, err := parseAndRoll("1d20adv")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result < 1 || result > 20 {
			t.Errorf("1d20adv result %d out of range [1,20]", result)
		}
		if !strings.Contains(detail, "->") {
			t.Errorf("advantage detail %q should contain '->'", detail)
		}
	}
}

// TestParseAndRollDisadvantage tests that 1d20dis result is within [1,20].
func TestParseAndRollDisadvantage(t *testing.T) {
	for i := 0; i < 30; i++ {
		result, detail, err := parseAndRoll("1d20dis")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result < 1 || result > 20 {
			t.Errorf("1d20dis result %d out of range [1,20]", result)
		}
		if !strings.Contains(detail, "->") {
			t.Errorf("disadvantage detail %q should contain '->'", detail)
		}
	}
}

// TestParseAndRollKeepHighest tests 4d6kh3 (stat generation).
func TestParseAndRollKeepHighest(t *testing.T) {
	for i := 0; i < 20; i++ {
		result, detail, err := parseAndRoll("4d6kh3")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		// Keep highest 3 of 4d6: min=3, max=18
		if result < 3 || result > 18 {
			t.Errorf("4d6kh3 result %d out of range [3,18]", result)
		}
		if !strings.Contains(detail, "kh3") {
			t.Errorf("keep-highest detail %q should contain 'kh3'", detail)
		}
	}
}

// TestParseAndRollKeepHighestClampedToCount tests kh > count is clamped.
func TestParseAndRollKeepHighestClampedToCount(t *testing.T) {
	// 2d6kh5 — keep highest 5, but only 2 dice: should keep all 2
	result, _, err := parseAndRoll("2d6kh5")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result < 2 || result > 12 {
		t.Errorf("2d6kh5 result %d out of range [2,12]", result)
	}
}

// TestParseAndRollInvalidFormula tests unrecognized formula returns error.
func TestParseAndRollInvalidFormula(t *testing.T) {
	cases := []string{
		"",
		"notdice",
		"d20", // missing count
		"2d",  // missing sides
		"abc",
		"1d1000000", // sides > 1000
		"101d6",     // count > 100
	}
	for _, formula := range cases {
		_, _, err := parseAndRoll(formula)
		if err == nil {
			t.Errorf("expected error for formula %q but got none", formula)
		}
	}
}

// TestParseAndRollCaseInsensitive tests that formula is normalized to lowercase.
func TestParseAndRollCaseInsensitive(t *testing.T) {
	_, _, err := parseAndRoll("2D6")
	if err != nil {
		t.Errorf("unexpected error for uppercase formula: %v", err)
	}
}

// TestParseAndRollBoundaryDice tests edge values of valid dice.
func TestParseAndRollBoundaryDice(t *testing.T) {
	// Minimum valid: 1d1 always returns 1
	result, _, err := parseAndRoll("1d1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != 1 {
		t.Errorf("1d1 should always be 1, got %d", result)
	}

	// Maximum valid die count and sides
	_, _, err = parseAndRoll("100d1000")
	if err != nil {
		t.Fatalf("100d1000 should be valid: %v", err)
	}
}

// TestSortDescCopy verifies the helper sorts a copy without mutating the original.
func TestSortDescCopy(t *testing.T) {
	original := []int{3, 1, 4, 1, 5, 9, 2, 6}
	sorted := sortDescCopy(original)

	// Verify descending order
	for i := 1; i < len(sorted); i++ {
		if sorted[i] > sorted[i-1] {
			t.Errorf("sortDescCopy: %v is not sorted descending", sorted)
		}
	}

	// Verify original is unchanged
	expected := []int{3, 1, 4, 1, 5, 9, 2, 6}
	for i, v := range original {
		if v != expected[i] {
			t.Errorf("sortDescCopy mutated original at index %d: got %d want %d", i, v, expected[i])
		}
	}
}

// TestSignStr verifies sign helper.
func TestSignStr(t *testing.T) {
	if signStr(5) != "+" {
		t.Error("signStr(5) should return '+'")
	}
	if signStr(0) != "+" {
		t.Error("signStr(0) should return '+'")
	}
	if signStr(-3) != "-" {
		t.Error("signStr(-3) should return '-'")
	}
}

// TestAbs verifies abs helper.
func TestAbs(t *testing.T) {
	if abs(7) != 7 {
		t.Error("abs(7) should return 7")
	}
	if abs(-7) != 7 {
		t.Error("abs(-7) should return 7")
	}
	if abs(0) != 0 {
		t.Error("abs(0) should return 0")
	}
}
