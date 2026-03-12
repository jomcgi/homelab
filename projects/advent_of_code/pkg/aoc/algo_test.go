package aoc

import (
	"testing"
)

func TestAbs(t *testing.T) {
	tests := []struct {
		in   int
		want int
	}{
		{5, 5},
		{-5, 5},
		{0, 0},
		{-1, 1},
		{100, 100},
	}
	for _, tt := range tests {
		if got := Abs(tt.in); got != tt.want {
			t.Errorf("Abs(%d) = %d, want %d", tt.in, got, tt.want)
		}
	}
}

func TestMod(t *testing.T) {
	tests := []struct {
		x, n int
		want int
	}{
		{7, 3, 1},
		{-1, 3, 2}, // Go's % returns -1, Mod returns 2
		{-4, 3, 2},
		{0, 5, 0},
		{9, 3, 0},
		{-3, 3, 0},
	}
	for _, tt := range tests {
		if got := Mod(tt.x, tt.n); got != tt.want {
			t.Errorf("Mod(%d, %d) = %d, want %d", tt.x, tt.n, got, tt.want)
		}
	}
}

func TestMin(t *testing.T) {
	tests := []struct {
		a, b int
		want int
	}{
		{1, 2, 1},
		{2, 1, 1},
		{3, 3, 3},
		{-5, -3, -5},
		{0, -1, -1},
	}
	for _, tt := range tests {
		if got := Min(tt.a, tt.b); got != tt.want {
			t.Errorf("Min(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
		}
	}
}

func TestMax(t *testing.T) {
	tests := []struct {
		a, b int
		want int
	}{
		{1, 2, 2},
		{2, 1, 2},
		{3, 3, 3},
		{-5, -3, -3},
		{0, -1, 0},
	}
	for _, tt := range tests {
		if got := Max(tt.a, tt.b); got != tt.want {
			t.Errorf("Max(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
		}
	}
}

func TestMinSlice(t *testing.T) {
	tests := []struct {
		s    []int
		want int
	}{
		{[]int{3, 1, 4, 1, 5}, 1},
		{[]int{10}, 10},
		{[]int{}, 0},
		{[]int{-3, -1, -4}, -4},
	}
	for _, tt := range tests {
		if got := MinSlice(tt.s); got != tt.want {
			t.Errorf("MinSlice(%v) = %d, want %d", tt.s, got, tt.want)
		}
	}
}

func TestMaxSlice(t *testing.T) {
	tests := []struct {
		s    []int
		want int
	}{
		{[]int{3, 1, 4, 1, 5}, 5},
		{[]int{10}, 10},
		{[]int{}, 0},
		{[]int{-3, -1, -4}, -1},
	}
	for _, tt := range tests {
		if got := MaxSlice(tt.s); got != tt.want {
			t.Errorf("MaxSlice(%v) = %d, want %d", tt.s, got, tt.want)
		}
	}
}

func TestSum(t *testing.T) {
	tests := []struct {
		s    []int
		want int
	}{
		{[]int{1, 2, 3}, 6},
		{[]int{}, 0},
		{[]int{-1, 1}, 0},
		{[]int{100}, 100},
	}
	for _, tt := range tests {
		if got := Sum(tt.s); got != tt.want {
			t.Errorf("Sum(%v) = %d, want %d", tt.s, got, tt.want)
		}
	}
}

func TestGCD(t *testing.T) {
	tests := []struct {
		a, b int
		want int
	}{
		{12, 8, 4},
		{7, 3, 1},
		{15, 5, 5},
		{0, 5, 5},
		{-12, 8, 4},
		{100, 75, 25},
	}
	for _, tt := range tests {
		if got := GCD(tt.a, tt.b); got != tt.want {
			t.Errorf("GCD(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
		}
	}
}

func TestLCM(t *testing.T) {
	tests := []struct {
		a, b int
		want int
	}{
		{4, 6, 12},
		{3, 5, 15},
		{0, 5, 0},
		{5, 0, 0},
		{7, 7, 7},
		{12, 8, 24},
	}
	for _, tt := range tests {
		if got := LCM(tt.a, tt.b); got != tt.want {
			t.Errorf("LCM(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
		}
	}
}

func TestLCMSlice(t *testing.T) {
	tests := []struct {
		s    []int
		want int
	}{
		{[]int{4, 6, 8}, 24},
		{[]int{3, 5, 7}, 105},
		{[]int{}, 0},
		{[]int{10}, 10},
	}
	for _, tt := range tests {
		if got := LCMSlice(tt.s); got != tt.want {
			t.Errorf("LCMSlice(%v) = %d, want %d", tt.s, got, tt.want)
		}
	}
}

func TestBFS(t *testing.T) {
	// Grid graph: points connected to neighbors
	grid := map[Point]bool{
		{0, 0}: true,
		{1, 0}: true,
		{2, 0}: true,
		{2, 1}: true,
	}

	neighbors := func(p Point) []Point {
		var result []Point
		for _, n := range p.Neighbors4() {
			if grid[n] {
				result = append(result, n)
			}
		}
		return result
	}

	start := Point{0, 0}
	distances := BFS(start, neighbors, func(Point, int) bool { return true })

	if distances[start] != 0 {
		t.Errorf("BFS start distance = %d, want 0", distances[start])
	}
	if d, ok := distances[Point{2, 0}]; !ok || d != 2 {
		t.Errorf("BFS distance to {2,0} = %d, ok=%v, want 2", d, ok)
	}
	if d, ok := distances[Point{2, 1}]; !ok || d != 3 {
		t.Errorf("BFS distance to {2,1} = %d, ok=%v, want 3", d, ok)
	}
	// Unreachable point
	if _, ok := distances[Point{5, 5}]; ok {
		t.Error("BFS should not reach {5,5}")
	}
}

func TestBFS_VisitStop(t *testing.T) {
	// BFS that stops at distance 1
	neighbors := func(p Point) []Point {
		return []Point{{p.X + 1, p.Y}, {p.X, p.Y + 1}}
	}

	visited := BFS(Point{0, 0}, neighbors, func(p Point, dist int) bool {
		return dist <= 1 // only explore from nodes at distance <=1
	})

	// Points at distance 0,1 should be in the map
	if _, ok := visited[Point{0, 0}]; !ok {
		t.Error("Expected start in visited")
	}
	if _, ok := visited[Point{1, 0}]; !ok {
		t.Error("Expected {1,0} in visited")
	}
}

func TestBFSPath(t *testing.T) {
	// Grid graph for path finding
	grid := map[Point]bool{
		{0, 0}: true, {1, 0}: true, {2, 0}: true,
		{2, 1}: true, {2, 2}: true,
	}
	neighbors := func(p Point) []Point {
		var result []Point
		for _, n := range p.Neighbors4() {
			if grid[n] {
				result = append(result, n)
			}
		}
		return result
	}

	// Existing path
	path, ok := BFSPath(Point{0, 0}, Point{2, 2}, neighbors)
	if !ok {
		t.Fatal("BFSPath expected to find path, got none")
	}
	if path[0] != (Point{0, 0}) {
		t.Errorf("Path start = %v, want {0,0}", path[0])
	}
	if path[len(path)-1] != (Point{2, 2}) {
		t.Errorf("Path end = %v, want {2,2}", path[len(path)-1])
	}
	if len(path) != 5 {
		t.Errorf("Path length = %d, want 5", len(path))
	}

	// Same start and end
	path, ok = BFSPath(Point{0, 0}, Point{0, 0}, neighbors)
	if !ok {
		t.Fatal("BFSPath start==end should return true")
	}
	if len(path) != 1 || path[0] != (Point{0, 0}) {
		t.Errorf("BFSPath same start/end: got %v", path)
	}

	// No path
	_, ok = BFSPath(Point{0, 0}, Point{9, 9}, neighbors)
	if ok {
		t.Error("BFSPath should return false for unreachable end")
	}
}

func TestDijkstra(t *testing.T) {
	// Weighted graph: edges with costs
	// A(0,0) -1-> B(1,0) -2-> C(2,0)
	//           |------5------->
	edges := map[[2]Point]int{
		{{0, 0}, {1, 0}}: 1,
		{{1, 0}, {2, 0}}: 2,
		{{0, 0}, {2, 0}}: 5,
	}
	neighbors := func(p Point) []Point {
		var result []Point
		for e := range edges {
			if e[0] == p {
				result = append(result, e[1])
			}
		}
		return result
	}
	cost := func(from, to Point) int {
		return edges[[2]Point{from, to}]
	}

	dist := Dijkstra(Point{0, 0}, neighbors, cost)
	if dist[Point{0, 0}] != 0 {
		t.Errorf("Dijkstra start dist = %d, want 0", dist[Point{0, 0}])
	}
	if dist[Point{1, 0}] != 1 {
		t.Errorf("Dijkstra {1,0} dist = %d, want 1", dist[Point{1, 0}])
	}
	if dist[Point{2, 0}] != 3 { // via {1,0}: 1+2=3, cheaper than 5
		t.Errorf("Dijkstra {2,0} dist = %d, want 3", dist[Point{2, 0}])
	}
}

func TestFloodFill(t *testing.T) {
	// 3x3 grid with a wall at {1,1}
	walls := map[Point]bool{{1, 1}: true}
	canVisit := func(p Point) bool {
		return p.X >= 0 && p.X < 3 && p.Y >= 0 && p.Y < 3 && !walls[p]
	}

	filled := FloodFill(Point{0, 0}, canVisit)

	// Should reach all non-wall cells accessible from {0,0}
	// {1,1} is a wall, but the flood fill navigates around it
	if !filled[Point{0, 0}] {
		t.Error("Expected {0,0} in flood fill")
	}
	if !filled[Point{2, 2}] {
		t.Error("Expected {2,2} in flood fill (reachable around the wall)")
	}
	if filled[Point{1, 1}] {
		t.Error("Wall {1,1} should not be in flood fill")
	}

	// Start on a wall
	result := FloodFill(Point{1, 1}, canVisit)
	if len(result) != 0 {
		t.Errorf("FloodFill starting on wall should be empty, got %v", result)
	}
}

func TestPermutations(t *testing.T) {
	// 3-element permutations: expect 6
	perms := Permutations([]int{1, 2, 3})
	if len(perms) != 6 {
		t.Errorf("Permutations(3) count = %d, want 6", len(perms))
	}

	// 1-element
	perms1 := Permutations([]int{42})
	if len(perms1) != 1 || perms1[0][0] != 42 {
		t.Errorf("Permutations(1) = %v, want [[42]]", perms1)
	}

	// Empty
	perms0 := Permutations([]int{})
	if len(perms0) != 1 {
		t.Errorf("Permutations(0) = %v, want [[]]", perms0)
	}

	// Verify no aliasing between permutations
	perms = Permutations([]int{1, 2})
	perms[0][0] = 99
	if perms[1][0] == 99 {
		t.Error("Permutations should not share underlying slices")
	}
}

func TestCombinations(t *testing.T) {
	// C(4,2) = 6
	combos := Combinations([]int{1, 2, 3, 4}, 2)
	if len(combos) != 6 {
		t.Errorf("Combinations(4,2) count = %d, want 6", len(combos))
	}

	// C(3,3) = 1
	combos3 := Combinations([]int{1, 2, 3}, 3)
	if len(combos3) != 1 {
		t.Errorf("Combinations(3,3) count = %d, want 1", len(combos3))
	}

	// C(3,0) = 1 (empty combination)
	combos0 := Combinations([]int{1, 2, 3}, 0)
	if len(combos0) != 1 {
		t.Errorf("Combinations(3,0) count = %d, want 1", len(combos0))
	}

	// k > n should return 0 combinations
	combosOver := Combinations([]int{1, 2}, 5)
	if len(combosOver) != 0 {
		t.Errorf("Combinations(2,5) count = %d, want 0", len(combosOver))
	}
}
