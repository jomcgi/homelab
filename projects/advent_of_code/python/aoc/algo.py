"""Algorithm utilities for Advent of Code."""

from __future__ import annotations
from collections import deque
from heapq import heappush, heappop
from itertools import (
    permutations as itertools_permutations,
    combinations as itertools_combinations,
)
from math import gcd
from functools import reduce
from typing import Callable, TypeVar, Hashable

from .grid import Point

__all__ = [
    "bfs",
    "bfs_path",
    "dijkstra",
    "flood_fill",
    "gcd",
    "lcm",
    "lcm_list",
    "permutations",
    "combinations",
    "sign",
    "clamp",
]

T = TypeVar("T", bound=Hashable)


def bfs(
    start: T,
    neighbors: Callable[[T], list[T]],
    visit: Callable[[T, int], bool] | None = None,
) -> dict[T, int]:
    """
    Perform breadth-first search from a starting point.

    Args:
        start: Starting node
        neighbors: Function returning valid neighbors for a node
        visit: Optional callback called for each node with its distance.
               Return False to stop exploring from that node.

    Returns:
        Dictionary mapping nodes to their distances from start.
    """
    distances: dict[T, int] = {start: 0}
    queue: deque[T] = deque([start])

    while queue:
        current = queue.popleft()
        dist = distances[current]

        if visit is not None and not visit(current, dist):
            continue

        for next_node in neighbors(current):
            if next_node not in distances:
                distances[next_node] = dist + 1
                queue.append(next_node)

    return distances


def bfs_path(
    start: T,
    end: T,
    neighbors: Callable[[T], list[T]],
) -> list[T] | None:
    """
    Find shortest path from start to end using BFS.

    Args:
        start: Starting node
        end: Target node
        neighbors: Function returning valid neighbors for a node

    Returns:
        List of nodes from start to end (inclusive), or None if no path exists.
    """
    if start == end:
        return [start]

    parent: dict[T, T] = {start: start}
    queue: deque[T] = deque([start])

    while queue:
        current = queue.popleft()

        for next_node in neighbors(current):
            if next_node not in parent:
                parent[next_node] = current
                if next_node == end:
                    # Reconstruct path
                    path = [end]
                    while path[-1] != start:
                        path.append(parent[path[-1]])
                    return path[::-1]
                queue.append(next_node)

    return None


def dijkstra(
    start: T,
    neighbors: Callable[[T], list[T]],
    cost: Callable[[T, T], int],
) -> dict[T, int]:
    """
    Find shortest paths from start using Dijkstra's algorithm.

    Args:
        start: Starting node
        neighbors: Function returning neighbors for a node
        cost: Function returning cost to move from one node to another
              (return 0 or negative for no edge)

    Returns:
        Dictionary mapping nodes to their minimum distances from start.
    """
    dist: dict[T, int] = {start: 0}
    heap: list[tuple[int, T]] = [(0, start)]

    while heap:
        current_dist, current = heappop(heap)

        if current in dist and current_dist > dist[current]:
            continue

        for next_node in neighbors(current):
            c = cost(current, next_node)
            if c <= 0:
                continue
            new_dist = current_dist + c
            if next_node not in dist or new_dist < dist[next_node]:
                dist[next_node] = new_dist
                heappush(heap, (new_dist, next_node))

    return dist


def flood_fill(
    start: Point,
    can_visit: Callable[[Point], bool],
) -> set[Point]:
    """
    Perform flood fill from start, returning all connected points.

    Args:
        start: Starting point
        can_visit: Function determining if a point can be visited

    Returns:
        Set of all visited points.
    """
    visited: set[Point] = set()
    if not can_visit(start):
        return visited

    stack = [start]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)

        for neighbor in current.neighbors4():
            if neighbor not in visited and can_visit(neighbor):
                stack.append(neighbor)

    return visited


def lcm(a: int, b: int) -> int:
    """Return least common multiple of a and b."""
    return abs(a * b) // gcd(a, b)


def lcm_list(values: list[int]) -> int:
    """Return LCM of all values in list."""
    return reduce(lcm, values)


def permutations(items: list[T]) -> list[list[T]]:
    """Generate all permutations of items."""
    return [list(p) for p in itertools_permutations(items)]


def combinations(items: list[T], k: int) -> list[list[T]]:
    """Generate all k-combinations of items."""
    return [list(c) for c in itertools_combinations(items, k)]


def sign(x: int) -> int:
    """Return sign of x: -1, 0, or 1."""
    if x < 0:
        return -1
    if x > 0:
        return 1
    return 0


def clamp(x: int, lo: int, hi: int) -> int:
    """Clamp x to range [lo, hi]."""
    return max(lo, min(hi, x))
