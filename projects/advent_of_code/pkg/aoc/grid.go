package aoc

import "strings"

// Point represents a 2D coordinate
type Point struct {
	X, Y int
}

func (p Point) Add(other Point) Point {
	return Point{p.X + other.X, p.Y + other.Y}
}

func (p Point) Sub(other Point) Point {
	return Point{p.X - other.X, p.Y - other.Y}
}

// Manhattan returns the Manhattan distance from origin
func (p Point) Manhattan() int {
	return Abs(p.X) + Abs(p.Y)
}

// ManhattanTo returns the Manhattan distance to another point
func (p Point) ManhattanTo(other Point) int {
	return Abs(p.X-other.X) + Abs(p.Y-other.Y)
}

// Neighbors4 returns the 4 cardinal neighbors (up, down, left, right)
func (p Point) Neighbors4() []Point {
	return []Point{
		{p.X, p.Y - 1}, // up
		{p.X, p.Y + 1}, // down
		{p.X - 1, p.Y}, // left
		{p.X + 1, p.Y}, // right
	}
}

// Neighbors8 returns all 8 neighbors including diagonals
func (p Point) Neighbors8() []Point {
	return []Point{
		{p.X, p.Y - 1},     // up
		{p.X, p.Y + 1},     // down
		{p.X - 1, p.Y},     // left
		{p.X + 1, p.Y},     // right
		{p.X - 1, p.Y - 1}, // up-left
		{p.X + 1, p.Y - 1}, // up-right
		{p.X - 1, p.Y + 1}, // down-left
		{p.X + 1, p.Y + 1}, // down-right
	}
}

// Direction constants
var (
	Up    = Point{0, -1}
	Down  = Point{0, 1}
	Left  = Point{-1, 0}
	Right = Point{1, 0}

	// Cardinal directions
	Directions4 = []Point{Up, Down, Left, Right}

	// All 8 directions
	Directions8 = []Point{
		Up, Down, Left, Right,
		{-1, -1},
		{1, -1},
		{-1, 1},
		{1, 1},
	}
)

// TurnLeft rotates a direction 90 degrees counter-clockwise
func TurnLeft(dir Point) Point {
	return Point{dir.Y, -dir.X}
}

// TurnRight rotates a direction 90 degrees clockwise
func TurnRight(dir Point) Point {
	return Point{-dir.Y, dir.X}
}

// Grid represents a 2D grid of runes
type Grid struct {
	Data   [][]rune
	Width  int
	Height int
}

func NewGrid(lines []string) *Grid {
	if len(lines) == 0 {
		return &Grid{}
	}

	height := len(lines)
	width := len(lines[0])
	data := make([][]rune, height)

	for y, line := range lines {
		data[y] = []rune(line)
		if len(data[y]) > width {
			width = len(data[y])
		}
	}

	return &Grid{
		Data:   data,
		Width:  width,
		Height: height,
	}
}

func NewGridFromString(s string) *Grid {
	return NewGrid(Lines(s))
}

// Get returns the rune at position, or 0 (null rune) if out of bounds.
func (g *Grid) Get(p Point) rune {
	if !g.InBounds(p) {
		return 0
	}
	if p.X >= len(g.Data[p.Y]) {
		return 0
	}
	return g.Data[p.Y][p.X]
}

func (g *Grid) Set(p Point, r rune) {
	if g.InBounds(p) {
		g.Data[p.Y][p.X] = r
	}
}

func (g *Grid) InBounds(p Point) bool {
	return p.X >= 0 && p.X < g.Width && p.Y >= 0 && p.Y < g.Height
}

// Find returns the first position of the given rune, or (-1,-1) if not found
func (g *Grid) Find(r rune) Point {
	for y, row := range g.Data {
		for x, cell := range row {
			if cell == r {
				return Point{x, y}
			}
		}
	}
	return Point{-1, -1}
}

// FindAll returns all positions containing the given rune
func (g *Grid) FindAll(r rune) []Point {
	var result []Point
	for y, row := range g.Data {
		for x, cell := range row {
			if cell == r {
				result = append(result, Point{x, y})
			}
		}
	}
	return result
}

func (g *Grid) ForEach(fn func(p Point, r rune)) {
	for y, row := range g.Data {
		for x, cell := range row {
			fn(Point{x, y}, cell)
		}
	}
}

// Copy creates a deep copy of the grid
func (g *Grid) Copy() *Grid {
	data := make([][]rune, g.Height)
	for y, row := range g.Data {
		data[y] = make([]rune, len(row))
		copy(data[y], row)
	}
	return &Grid{
		Data:   data,
		Width:  g.Width,
		Height: g.Height,
	}
}

func (g *Grid) String() string {
	var sb strings.Builder
	for _, row := range g.Data {
		sb.WriteString(string(row))
		sb.WriteRune('\n')
	}
	return sb.String()
}

// Count returns the number of cells matching the predicate
func (g *Grid) Count(fn func(r rune) bool) int {
	count := 0
	g.ForEach(func(p Point, r rune) {
		if fn(r) {
			count++
		}
	})
	return count
}

func (g *Grid) CountRune(r rune) int {
	return g.Count(func(c rune) bool { return c == r })
}
