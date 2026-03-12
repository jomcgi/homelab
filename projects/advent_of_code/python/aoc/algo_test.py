"""Tests for aoc.algo module."""

import pytest

from projects.advent_of_code.python.aoc.algo import (
    bfs,
    bfs_path,
    clamp,
    combinations,
    dijkstra,
    flood_fill,
    lcm,
    lcm_list,
    permutations,
    sign,
)
from projects.advent_of_code.python.aoc.grid import Point


# --- bfs ---


def test_bfs_simple_grid():
    """BFS finds correct distances in a small grid."""
    reachable = {(0, 0), (1, 0), (2, 0), (2, 1)}

    def neighbors(p):
        x, y = p
        return [
            (nx, ny)
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            if (nx, ny) in reachable
        ]

    distances = bfs((0, 0), neighbors)
    assert distances[(0, 0)] == 0
    assert distances[(2, 0)] == 2
    assert distances[(2, 1)] == 3


def test_bfs_visit_stops_exploration():
    """BFS visit callback can stop exploring from a node."""

    def neighbors(p):
        x, y = p
        return [(x + 1, y), (x, y + 1)]

    # Only explore from nodes at distance <= 1
    visited = bfs((0, 0), neighbors, visit=lambda p, d: d <= 1)
    assert (0, 0) in visited
    assert (1, 0) in visited
    assert (0, 1) in visited


def test_bfs_no_visit_callback():
    """BFS works without a visit callback."""

    def neighbors(p):
        x, y = p
        return [(x + 1, y)] if x < 2 else []

    distances = bfs((0, 0), neighbors)
    assert distances[(1, 0)] == 1
    assert distances[(2, 0)] == 2


# --- bfs_path ---


def test_bfs_path_finds_shortest():
    """bfs_path returns shortest path."""
    reachable = {(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)}

    def neighbors(p):
        x, y = p
        return [
            (nx, ny)
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            if (nx, ny) in reachable
        ]

    path = bfs_path((0, 0), (2, 2), neighbors)
    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (2, 2)
    assert len(path) == 5


def test_bfs_path_same_start_end():
    """bfs_path with same start and end returns single-element list."""
    path = bfs_path((1, 1), (1, 1), lambda p: [])
    assert path == [(1, 1)]


def test_bfs_path_no_path():
    """bfs_path returns None when no path exists."""
    result = bfs_path((0, 0), (9, 9), lambda p: [])
    assert result is None


# --- dijkstra ---


def test_dijkstra_weighted():
    """Dijkstra finds minimum-cost paths with weighted edges."""
    # A->B cost 1, B->C cost 2, A->C cost 5 (via B is cheaper: 3)
    edges = {((0, 0), (1, 0)): 1, ((1, 0), (2, 0)): 2, ((0, 0), (2, 0)): 5}

    def neighbors(p):
        return [e[1] for e in edges if e[0] == p]

    def cost(a, b):
        return edges.get((a, b), 0)

    dist = dijkstra((0, 0), neighbors, cost)
    assert dist[(0, 0)] == 0
    assert dist[(1, 0)] == 1
    assert dist[(2, 0)] == 3  # via (1,0): 1+2=3


def test_dijkstra_skips_zero_cost_edges():
    """Dijkstra skips edges with cost <= 0."""

    def neighbors(p):
        return [(p[0] + 1, p[1])]

    def cost(a, b):
        return 0  # no valid edges

    dist = dijkstra((0, 0), neighbors, cost)
    assert (1, 0) not in dist


# --- flood_fill ---


def test_flood_fill_basic():
    """Flood fill visits all connected passable cells."""
    walls = {Point(1, 1)}

    def can_visit(p):
        return 0 <= p.x < 3 and 0 <= p.y < 3 and p not in walls

    filled = flood_fill(Point(0, 0), can_visit)
    assert Point(0, 0) in filled
    # {1,1} is a wall but {2,2} is reachable around it
    assert Point(2, 2) in filled
    assert Point(1, 1) not in filled


def test_flood_fill_start_on_wall():
    """Flood fill starting on impassable cell returns empty set."""
    result = flood_fill(Point(0, 0), lambda p: False)
    assert result == set()


# --- lcm ---


def test_lcm():
    assert lcm(4, 6) == 12
    assert lcm(3, 5) == 15
    assert lcm(7, 7) == 7
    assert lcm(12, 8) == 24


def test_lcm_list():
    assert lcm_list([4, 6, 8]) == 24
    assert lcm_list([3, 5, 7]) == 105
    assert lcm_list([10]) == 10


# --- permutations ---


def test_permutations_count():
    assert len(permutations([1, 2, 3])) == 6


def test_permutations_single():
    assert permutations([42]) == [[42]]


def test_permutations_empty():
    assert permutations([]) == [[]]


def test_permutations_no_aliasing():
    """Permutations should not share underlying lists."""
    perms = permutations([1, 2])
    perms[0][0] = 99
    assert perms[1][0] != 99


# --- combinations ---


def test_combinations_count():
    assert len(combinations([1, 2, 3, 4], 2)) == 6


def test_combinations_full():
    assert len(combinations([1, 2, 3], 3)) == 1


def test_combinations_empty_k():
    assert len(combinations([1, 2, 3], 0)) == 1


def test_combinations_k_larger_than_n():
    assert len(combinations([1, 2], 5)) == 0


# --- sign ---


def test_sign():
    assert sign(-10) == -1
    assert sign(0) == 0
    assert sign(10) == 1


# --- clamp ---


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-5, 0, 10) == 0
    assert clamp(15, 0, 10) == 10
    assert clamp(0, 0, 0) == 0
