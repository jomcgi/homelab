"""Grid and 2D coordinate utilities for Advent of Code."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterator

__all__ = [
    "Point",
    "Grid",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "DIRECTIONS4",
    "DIRECTIONS8",
    "turn_left",
    "turn_right",
]


@dataclass(frozen=True, slots=True)
class Point:
    """A 2D coordinate."""

    x: int
    y: int

    def __add__(self, other: Point) -> Point:
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: int) -> Point:
        return Point(self.x * scalar, self.y * scalar)

    def __neg__(self) -> Point:
        return Point(-self.x, -self.y)

    def manhattan(self) -> int:
        """Manhattan distance from origin."""
        return abs(self.x) + abs(self.y)

    def manhattan_to(self, other: Point) -> int:
        """Manhattan distance to another point."""
        return abs(self.x - other.x) + abs(self.y - other.y)

    def neighbors4(self) -> list[Point]:
        """Return 4 cardinal neighbors (up, down, left, right)."""
        return [
            Point(self.x, self.y - 1),  # up
            Point(self.x, self.y + 1),  # down
            Point(self.x - 1, self.y),  # left
            Point(self.x + 1, self.y),  # right
        ]

    def neighbors8(self) -> list[Point]:
        """Return all 8 neighbors including diagonals."""
        return [
            Point(self.x, self.y - 1),  # up
            Point(self.x, self.y + 1),  # down
            Point(self.x - 1, self.y),  # left
            Point(self.x + 1, self.y),  # right
            Point(self.x - 1, self.y - 1),  # up-left
            Point(self.x + 1, self.y - 1),  # up-right
            Point(self.x - 1, self.y + 1),  # down-left
            Point(self.x + 1, self.y + 1),  # down-right
        ]

    def __iter__(self):
        """Allow unpacking: x, y = point"""
        yield self.x
        yield self.y


# Direction constants
UP = Point(0, -1)
DOWN = Point(0, 1)
LEFT = Point(-1, 0)
RIGHT = Point(1, 0)

DIRECTIONS4 = [UP, DOWN, LEFT, RIGHT]
DIRECTIONS8 = [
    UP,
    DOWN,
    LEFT,
    RIGHT,
    Point(-1, -1),
    Point(1, -1),
    Point(-1, 1),
    Point(1, 1),
]


def turn_left(direction: Point) -> Point:
    """Rotate direction 90 degrees counter-clockwise."""
    return Point(direction.y, -direction.x)


def turn_right(direction: Point) -> Point:
    """Rotate direction 90 degrees clockwise."""
    return Point(-direction.y, direction.x)


class Grid:
    """A 2D grid of characters."""

    def __init__(self, data: list[list[str]]):
        self.data = data
        self.height = len(data)
        self.width = max(len(row) for row in data) if data else 0

    @classmethod
    def from_string(cls, s: str) -> Grid:
        """Create grid from multi-line string."""
        lines = s.rstrip("\n").split("\n")
        return cls([list(line) for line in lines])

    @classmethod
    def from_lines(cls, lines: list[str]) -> Grid:
        """Create grid from list of strings."""
        return cls([list(line) for line in lines])

    @classmethod
    def empty(cls, width: int, height: int, fill: str = ".") -> Grid:
        """Create an empty grid filled with a character."""
        return cls([[fill] * width for _ in range(height)])

    def get(self, p: Point, default: str = "") -> str:
        """Get character at position, or default if out of bounds."""
        if not self.in_bounds(p):
            return default
        if p.x >= len(self.data[p.y]):
            return default
        return self.data[p.y][p.x]

    def __getitem__(self, p: Point) -> str:
        """Get character at position. Raises IndexError if out of bounds."""
        if not self.in_bounds(p):
            raise IndexError(f"Point {p} out of bounds")
        return self.data[p.y][p.x]

    def set(self, p: Point, value: str) -> None:
        """Set character at position."""
        if self.in_bounds(p):
            self.data[p.y][p.x] = value

    def __setitem__(self, p: Point, value: str) -> None:
        """Set character at position."""
        self.set(p, value)

    def in_bounds(self, p: Point) -> bool:
        """Check if point is within grid bounds."""
        return 0 <= p.x < self.width and 0 <= p.y < self.height

    def find(self, char: str) -> Point | None:
        """Find first occurrence of character, or None if not found."""
        for y, row in enumerate(self.data):
            for x, cell in enumerate(row):
                if cell == char:
                    return Point(x, y)
        return None

    def find_all(self, char: str) -> list[Point]:
        """Find all occurrences of character."""
        result = []
        for y, row in enumerate(self.data):
            for x, cell in enumerate(row):
                if cell == char:
                    result.append(Point(x, y))
        return result

    def __iter__(self) -> Iterator[tuple[Point, str]]:
        """Iterate over all (point, character) pairs."""
        for y, row in enumerate(self.data):
            for x, cell in enumerate(row):
                yield Point(x, y), cell

    def copy(self) -> Grid:
        """Create a deep copy of the grid."""
        return Grid([row.copy() for row in self.data])

    def __str__(self) -> str:
        """Convert grid back to string."""
        return "\n".join("".join(row) for row in self.data)

    def count(self, predicate: Callable[[str], bool]) -> int:
        """Count cells matching predicate."""
        return sum(1 for _, cell in self if predicate(cell))

    def count_char(self, char: str) -> int:
        """Count occurrences of character."""
        return self.count(lambda c: c == char)

    def neighbors4_valid(self, p: Point) -> list[Point]:
        """Return valid 4-neighbors within bounds."""
        return [n for n in p.neighbors4() if self.in_bounds(n)]

    def neighbors8_valid(self, p: Point) -> list[Point]:
        """Return valid 8-neighbors within bounds."""
        return [n for n in p.neighbors8() if self.in_bounds(n)]
