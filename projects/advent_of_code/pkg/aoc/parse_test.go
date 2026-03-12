package aoc

import (
	"reflect"
	"testing"
)

func TestLines(t *testing.T) {
	tests := []struct {
		in   string
		want []string
	}{
		{"a\nb\nc", []string{"a", "b", "c"}},
		{"a\nb\nc\n", []string{"a", "b", "c"}},   // trailing newline stripped
		{"a\nb\nc\n\n", []string{"a", "b", "c"}}, // multiple trailing newlines stripped
		{"", nil},
		{"\n", nil},
		{"single", []string{"single"}},
	}
	for _, tt := range tests {
		got := Lines(tt.in)
		if !reflect.DeepEqual(got, tt.want) {
			t.Errorf("Lines(%q) = %v, want %v", tt.in, got, tt.want)
		}
	}
}

func TestParagraphs(t *testing.T) {
	tests := []struct {
		in   string
		want []string
	}{
		{"a\nb\n\nc\nd", []string{"a\nb", "c\nd"}},
		{"  \n  ", nil}, // only whitespace
		{"single", []string{"single"}},
		{"", nil},
	}
	for _, tt := range tests {
		got := Paragraphs(tt.in)
		if !reflect.DeepEqual(got, tt.want) {
			t.Errorf("Paragraphs(%q) = %v, want %v", tt.in, got, tt.want)
		}
	}
}

func TestInts(t *testing.T) {
	tests := []struct {
		in   string
		want []int
	}{
		{"1 2 3", []int{1, 2, 3}},
		{"-1 -2 -3", []int{-1, -2, -3}},
		{"foo 42 bar -7 baz", []int{42, -7}},
		{"no numbers here", nil},
		{"100", []int{100}},
		{"1,2,3", []int{1, 2, 3}},
		{"x=-5,y=10", []int{-5, 10}},
	}
	for _, tt := range tests {
		got := Ints(tt.in)
		if !reflect.DeepEqual(got, tt.want) {
			t.Errorf("Ints(%q) = %v, want %v", tt.in, got, tt.want)
		}
	}
}

func TestMustInt(t *testing.T) {
	if got := MustInt("42"); got != 42 {
		t.Errorf("MustInt(\"42\") = %d, want 42", got)
	}
	if got := MustInt("-7"); got != -7 {
		t.Errorf("MustInt(\"-7\") = %d, want -7", got)
	}
	if got := MustInt("  10  "); got != 10 {
		t.Errorf("MustInt(\"  10  \") = %d, want 10", got)
	}

	defer func() {
		if r := recover(); r == nil {
			t.Error("MustInt invalid should panic")
		}
	}()
	MustInt("notanumber")
}

func TestMustInts(t *testing.T) {
	got := MustInts([]string{"1", "2", "3"})
	want := []int{1, 2, 3}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("MustInts = %v, want %v", got, want)
	}
}

func TestFields(t *testing.T) {
	got := Fields("  hello   world  ")
	want := []string{"hello", "world"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Fields = %v, want %v", got, want)
	}
}

func TestSplit(t *testing.T) {
	tests := []struct {
		in, sep string
		want    []string
	}{
		{"a, b, c", ",", []string{"a", "b", "c"}},
		{"a:b:c", ":", []string{"a", "b", "c"}},
		{"  a |  | b  ", "|", []string{"a", "b"}}, // empty parts removed
		{"", ",", nil},
	}
	for _, tt := range tests {
		got := Split(tt.in, tt.sep)
		if !reflect.DeepEqual(got, tt.want) {
			t.Errorf("Split(%q, %q) = %v, want %v", tt.in, tt.sep, got, tt.want)
		}
	}
}

func TestChars(t *testing.T) {
	got := Chars("abc")
	want := []string{"a", "b", "c"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Chars(\"abc\") = %v, want %v", got, want)
	}
	if len(Chars("")) != 0 {
		t.Error("Chars(\"\") should be empty")
	}
}

func TestRunes(t *testing.T) {
	got := Runes("abc")
	if len(got) != 3 || got[0] != 'a' || got[1] != 'b' || got[2] != 'c' {
		t.Errorf("Runes(\"abc\") = %v, unexpected", got)
	}
}
