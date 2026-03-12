package aoc

import (
	"strings"
	"testing"
)

func TestPoint_Add(t *testing.T) {
	a := Point{1, 2}
	b := Point{3, 4}
	got := a.Add(b)
	want := Point{4, 6}
	if got != want {
		t.Errorf("Point.Add: got %v, want %v", got, want)
	}
}

func TestPoint_Sub(t *testing.T) {
	a := Point{5, 3}
	b := Point{2, 1}
	got := a.Sub(b)
	want := Point{3, 2}
	if got != want {
		t.Errorf("Point.Sub: got %v, want %v", got, want)
	}
}

func TestPoint_Manhattan(t *testing.T) {
	tests := []struct {
		p    Point
		want int
	}{
		{Point{0, 0}, 0},
		{Point{3, 4}, 7},
		{Point{-3, 4}, 7},
		{Point{-3, -4}, 7},
	}
	for _, tt := range tests {
		if got := tt.p.Manhattan(); got != tt.want {
			t.Errorf("Point%v.Manhattan() = %d, want %d", tt.p, got, tt.want)
		}
	}
}

func TestPoint_ManhattanTo(t *testing.T) {
	a := Point{1, 1}
	b := Point{4, 5}
	// |4-1| + |5-1| = 3 + 4 = 7
	if got := a.ManhattanTo(b); got != 7 {
		t.Errorf("ManhattanTo = %d, want 7", got)
	}
	if got := b.ManhattanTo(a); got != 7 {
		t.Errorf("ManhattanTo (reversed) = %d, want 7", got)
	}
}

func TestPoint_Neighbors4(t *testing.T) {
	p := Point{2, 3}
	neighbors := p.Neighbors4()
	if len(neighbors) != 4 {
		t.Fatalf("Neighbors4 count = %d, want 4", len(neighbors))
	}
	expected := map[Point]bool{
		{2, 2}: true, // up
		{2, 4}: true, // down
		{1, 3}: true, // left
		{3, 3}: true, // right
	}
	for _, n := range neighbors {
		if !expected[n] {
			t.Errorf("Unexpected neighbor: %v", n)
		}
	}
}

func TestPoint_Neighbors8(t *testing.T) {
	p := Point{2, 3}
	neighbors := p.Neighbors8()
	if len(neighbors) != 8 {
		t.Fatalf("Neighbors8 count = %d, want 8", len(neighbors))
	}
}

func TestTurnLeft(t *testing.T) {
	// Right -> Up (CCW)
	tests := []struct {
		dir  Point
		want Point
	}{
		{Right, Up},
		{Up, Left},
		{Left, Down},
		{Down, Right},
	}
	for _, tt := range tests {
		if got := TurnLeft(tt.dir); got != tt.want {
			t.Errorf("TurnLeft(%v) = %v, want %v", tt.dir, got, tt.want)
		}
	}
}

func TestTurnRight(t *testing.T) {
	// Right -> Down (CW)
	tests := []struct {
		dir  Point
		want Point
	}{
		{Right, Down},
		{Down, Left},
		{Left, Up},
		{Up, Right},
	}
	for _, tt := range tests {
		if got := TurnRight(tt.dir); got != tt.want {
			t.Errorf("TurnRight(%v) = %v, want %v", tt.dir, got, tt.want)
		}
	}
}

func TestNewGrid(t *testing.T) {
	lines := []string{"abc", "def", "ghi"}
	g := NewGrid(lines)

	if g.Width != 3 {
		t.Errorf("Width = %d, want 3", g.Width)
	}
	if g.Height != 3 {
		t.Errorf("Height = %d, want 3", g.Height)
	}
	if g.Get(Point{0, 0}) != 'a' {
		t.Errorf("Get(0,0) = %c, want 'a'", g.Get(Point{0, 0}))
	}
	if g.Get(Point{2, 2}) != 'i' {
		t.Errorf("Get(2,2) = %c, want 'i'", g.Get(Point{2, 2}))
	}

	// Empty grid
	empty := NewGrid(nil)
	if empty.Width != 0 || empty.Height != 0 {
		t.Errorf("Empty grid: Width=%d Height=%d, want 0,0", empty.Width, empty.Height)
	}
}

func TestNewGridFromString(t *testing.T) {
	s := "ab\ncd\n"
	g := NewGridFromString(s)
	if g.Width != 2 || g.Height != 2 {
		t.Errorf("Grid size = %dx%d, want 2x2", g.Width, g.Height)
	}
	if g.Get(Point{1, 1}) != 'd' {
		t.Errorf("Get(1,1) = %c, want 'd'", g.Get(Point{1, 1}))
	}
}

func TestGrid_InBounds(t *testing.T) {
	g := NewGrid([]string{"abc", "def"})
	tests := []struct {
		p    Point
		want bool
	}{
		{Point{0, 0}, true},
		{Point{2, 1}, true},
		{Point{3, 0}, false}, // out right
		{Point{0, 2}, false}, // out bottom
		{Point{-1, 0}, false},
		{Point{0, -1}, false},
	}
	for _, tt := range tests {
		if got := g.InBounds(tt.p); got != tt.want {
			t.Errorf("InBounds(%v) = %v, want %v", tt.p, got, tt.want)
		}
	}
}

func TestGrid_Get_OutOfBounds(t *testing.T) {
	g := NewGrid([]string{"abc"})
	// Out-of-bounds returns null rune (0)
	if got := g.Get(Point{5, 5}); got != 0 {
		t.Errorf("Get(out-of-bounds) = %v, want null rune", got)
	}
}

func TestGrid_Set(t *testing.T) {
	g := NewGrid([]string{"abc", "def"})
	g.Set(Point{1, 0}, 'X')
	if g.Get(Point{1, 0}) != 'X' {
		t.Errorf("After Set, Get(1,0) = %c, want 'X'", g.Get(Point{1, 0}))
	}
	// Out-of-bounds Set is a no-op
	g.Set(Point{10, 10}, 'Z') // should not panic
}

func TestGrid_Find(t *testing.T) {
	g := NewGrid([]string{"abc", "dXf"})
	p := g.Find('X')
	if p != (Point{1, 1}) {
		t.Errorf("Find('X') = %v, want {1,1}", p)
	}
	// Not found
	notFound := g.Find('Z')
	if notFound != (Point{-1, -1}) {
		t.Errorf("Find('Z') = %v, want {-1,-1}", notFound)
	}
}

func TestGrid_FindAll(t *testing.T) {
	g := NewGrid([]string{"aXb", "cXd"})
	pts := g.FindAll('X')
	if len(pts) != 2 {
		t.Fatalf("FindAll('X') count = %d, want 2", len(pts))
	}
}

func TestGrid_Count(t *testing.T) {
	g := NewGrid([]string{"aaB", "Baa"})
	count := g.CountRune('a')
	if count != 4 {
		t.Errorf("CountRune('a') = %d, want 4", count)
	}
	count = g.CountRune('B')
	if count != 2 {
		t.Errorf("CountRune('B') = %d, want 2", count)
	}
}

func TestGrid_Copy(t *testing.T) {
	g := NewGrid([]string{"abc"})
	cp := g.Copy()
	cp.Set(Point{0, 0}, 'Z')
	// Original should be unchanged
	if g.Get(Point{0, 0}) != 'a' {
		t.Error("Copy.Set mutated original grid")
	}
}

func TestGrid_String(t *testing.T) {
	lines := []string{"abc", "def"}
	g := NewGrid(lines)
	s := g.String()
	if !strings.Contains(s, "abc") || !strings.Contains(s, "def") {
		t.Errorf("Grid.String() = %q, expected to contain rows", s)
	}
}

func TestGrid_ForEach(t *testing.T) {
	g := NewGrid([]string{"ab", "cd"})
	count := 0
	g.ForEach(func(p Point, r rune) {
		count++
	})
	if count != 4 {
		t.Errorf("ForEach visited %d cells, want 4", count)
	}
}
