package aoc

import (
	"container/heap"
)

func Abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

// Mod returns x mod n, always non-negative (unlike Go's % operator).
func Mod(x, n int) int {
	return ((x % n) + n) % n
}

func Min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func Max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func MinSlice(s []int) int {
	if len(s) == 0 {
		return 0
	}
	m := s[0]
	for _, v := range s[1:] {
		if v < m {
			m = v
		}
	}
	return m
}

func MaxSlice(s []int) int {
	if len(s) == 0 {
		return 0
	}
	m := s[0]
	for _, v := range s[1:] {
		if v > m {
			m = v
		}
	}
	return m
}

func Sum(s []int) int {
	total := 0
	for _, v := range s {
		total += v
	}
	return total
}

// GCD returns the greatest common divisor of a and b
func GCD(a, b int) int {
	for b != 0 {
		a, b = b, a%b
	}
	return Abs(a)
}

// LCM returns the least common multiple of a and b
func LCM(a, b int) int {
	if a == 0 || b == 0 {
		return 0
	}
	return Abs(a*b) / GCD(a, b)
}

func LCMSlice(values []int) int {
	if len(values) == 0 {
		return 0
	}
	result := values[0]
	for _, v := range values[1:] {
		result = LCM(result, v)
	}
	return result
}

// BFS performs breadth-first search from a starting point
// neighbors returns the valid neighbors for a given point
// visit is called for each visited point with its distance from start
// Returns a map of points to their distances
func BFS(start Point, neighbors func(Point) []Point, visit func(Point, int) bool) map[Point]int {
	distances := make(map[Point]int)
	distances[start] = 0

	queue := []Point{start}
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		dist := distances[current]

		if !visit(current, dist) {
			continue
		}

		for _, next := range neighbors(current) {
			if _, seen := distances[next]; !seen {
				distances[next] = dist + 1
				queue = append(queue, next)
			}
		}
	}

	return distances
}

// BFSPath finds the shortest path from start to end using BFS
// Returns the path (including start and end) and whether a path was found
func BFSPath(start, end Point, neighbors func(Point) []Point) ([]Point, bool) {
	if start == end {
		return []Point{start}, true
	}

	parent := make(map[Point]Point)
	parent[start] = start

	queue := []Point{start}
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]

		for _, next := range neighbors(current) {
			if _, seen := parent[next]; !seen {
				parent[next] = current
				if next == end {
					// Reconstruct path
					path := []Point{end}
					for path[len(path)-1] != start {
						path = append(path, parent[path[len(path)-1]])
					}
					// Reverse path
					for i, j := 0, len(path)-1; i < j; i, j = i+1, j-1 {
						path[i], path[j] = path[j], path[i]
					}
					return path, true
				}
				queue = append(queue, next)
			}
		}
	}

	return nil, false
}

// Priority queue implementation for Dijkstra
type pqItem struct {
	point    Point
	priority int
	index    int
}

type priorityQueue []*pqItem

func (pq priorityQueue) Len() int           { return len(pq) }
func (pq priorityQueue) Less(i, j int) bool { return pq[i].priority < pq[j].priority }
func (pq priorityQueue) Swap(i, j int) {
	pq[i], pq[j] = pq[j], pq[i]
	pq[i].index = i
	pq[j].index = j
}

func (pq *priorityQueue) Push(x any) {
	n := len(*pq)
	item := x.(*pqItem)
	item.index = n
	*pq = append(*pq, item)
}

func (pq *priorityQueue) Pop() any {
	old := *pq
	n := len(old)
	item := old[n-1]
	old[n-1] = nil
	item.index = -1
	*pq = old[0 : n-1]
	return item
}

// Dijkstra finds shortest paths from start using weighted edges
// cost returns the cost to move from one point to another (0 or negative means no edge)
// Returns a map of points to their minimum distances from start
func Dijkstra(start Point, neighbors func(Point) []Point, cost func(from, to Point) int) map[Point]int {
	dist := make(map[Point]int)
	dist[start] = 0

	pq := &priorityQueue{{point: start, priority: 0}}
	heap.Init(pq)

	for pq.Len() > 0 {
		item := heap.Pop(pq).(*pqItem)
		current := item.point
		currentDist := item.priority

		if d, ok := dist[current]; ok && currentDist > d {
			continue
		}

		for _, next := range neighbors(current) {
			c := cost(current, next)
			if c <= 0 {
				continue
			}
			newDist := currentDist + c
			if d, ok := dist[next]; !ok || newDist < d {
				dist[next] = newDist
				heap.Push(pq, &pqItem{point: next, priority: newDist})
			}
		}
	}

	return dist
}

// FloodFill performs a flood fill from start, returning all connected points
// canVisit determines if a point can be visited
func FloodFill(start Point, canVisit func(Point) bool) map[Point]bool {
	visited := make(map[Point]bool)
	if !canVisit(start) {
		return visited
	}

	stack := []Point{start}
	for len(stack) > 0 {
		current := stack[len(stack)-1]
		stack = stack[:len(stack)-1]

		if visited[current] {
			continue
		}
		visited[current] = true

		for _, next := range current.Neighbors4() {
			if !visited[next] && canVisit(next) {
				stack = append(stack, next)
			}
		}
	}

	return visited
}

// Permutations generates all permutations of a slice
func Permutations[T any](arr []T) [][]T {
	var result [][]T
	permute(arr, 0, &result)
	return result
}

func permute[T any](arr []T, start int, result *[][]T) {
	if start == len(arr) {
		perm := make([]T, len(arr))
		copy(perm, arr)
		*result = append(*result, perm)
		return
	}
	for i := start; i < len(arr); i++ {
		arr[start], arr[i] = arr[i], arr[start]
		permute(arr, start+1, result)
		arr[start], arr[i] = arr[i], arr[start]
	}
}

// Combinations generates all k-combinations of a slice
func Combinations[T any](arr []T, k int) [][]T {
	var result [][]T
	combine(arr, k, 0, []T{}, &result)
	return result
}

func combine[T any](arr []T, k, start int, current []T, result *[][]T) {
	if len(current) == k {
		combo := make([]T, k)
		copy(combo, current)
		*result = append(*result, combo)
		return
	}
	for i := start; i < len(arr); i++ {
		combine(arr, k, i+1, append(current, arr[i]), result)
	}
}
