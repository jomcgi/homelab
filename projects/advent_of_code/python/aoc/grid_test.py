"""Tests for aoc.grid module."""

import pytest

from projects.advent_of_code.python.aoc.grid import (
    DIRECTIONS4,
    DIRECTIONS8,
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Grid,
    Point,
    turn_left,
    turn_right,
)


# --- Point ---

def test_point_add():
    assert Point(1, 2) + Point(3, 4) == Point(4, 6)


def test_point_sub():
    assert Point(5, 3) - Point(2, 1) == Point(3, 2)


def test_point_mul():
    assert Point(2, 3) * 4 == Point(8, 12)


def test_point_neg():
    assert -Point(3, -4) == Point(-3, 4)


def test_point_manhattan():
    assert Point(0, 0).manhattan() == 0
    assert Point(3, 4).manhattan() == 7
    assert Point(-3, 4).manhattan() == 7


def test_point_manhattan_to():
    a, b = Point(1, 1), Point(4, 5)
    assert a.manhattan_to(b) == 7
    assert b.manhattan_to(a) == 7


def test_point_neighbors4():
    p = Point(2, 3)
    ns = p.neighbors4()
    assert len(ns) == 4
    assert Point(2, 2) in ns  # up
    assert Point(2, 4) in ns  # down
    assert Point(1, 3) in ns  # left
    assert Point(3, 3) in ns  # right


def test_point_neighbors8():
    p = Point(2, 3)
    ns = p.neighbors8()
    assert len(ns) == 8


def test_point_iter_unpack():
    x, y = Point(7, 8)
    assert x == 7
    assert y == 8


def test_point_hashable():
    """Points should be usable as dict keys / set members."""
    d = {Point(0, 0): "origin"}
    assert d[Point(0, 0)] == "origin"
    s = {Point(1, 2), Point(1, 2)}
    assert len(s) == 1


# --- Direction constants ---

def test_directions4_length():
    assert len(DIRECTIONS4) == 4


def test_directions8_length():
    assert len(DIRECTIONS8) == 8


def test_up_down_left_right():
    assert UP == Point(0, -1)
    assert DOWN == Point(0, 1)
    assert LEFT == Point(-1, 0)
    assert RIGHT == Point(1, 0)


# --- turn_left / turn_right ---

def test_turn_left():
    assert turn_left(RIGHT) == UP
    assert turn_left(UP) == LEFT
    assert turn_left(LEFT) == DOWN
    assert turn_left(DOWN) == RIGHT


def test_turn_right():
    assert turn_right(RIGHT) == DOWN
    assert turn_right(DOWN) == LEFT
    assert turn_right(LEFT) == UP
    assert turn_right(UP) == RIGHT


# --- Grid ---

def test_grid_from_string():
    g = Grid.from_string("abc\ndef")
    assert g.width == 3
    assert g.height == 2
    assert g.get(Point(0, 0)) == "a"
    assert g.get(Point(2, 1)) == "f"


def test_grid_from_lines():
    g = Grid.from_lines(["ab", "cd"])
    assert g.width == 2
    assert g.height == 2


def test_grid_empty():
    g = Grid.empty(3, 2, ".")
    assert g.width == 3
    assert g.height == 2
    assert g.get(Point(1, 1)) == "."


def test_grid_in_bounds():
    g = Grid.from_string("abc\ndef")
    assert g.in_bounds(Point(0, 0))
    assert g.in_bounds(Point(2, 1))
    assert not g.in_bounds(Point(3, 0))
    assert not g.in_bounds(Point(0, 2))
    assert not g.in_bounds(Point(-1, 0))


def test_grid_get_out_of_bounds():
    g = Grid.from_string("abc")
    assert g.get(Point(10, 10)) == ""  # default
    assert g.get(Point(10, 10), default="X") == "X"


def test_grid_getitem():
    g = Grid.from_string("abc\ndef")
    assert g[Point(1, 0)] == "b"
    with pytest.raises(IndexError):
        _ = g[Point(10, 10)]


def test_grid_set():
    g = Grid.from_string("abc")
    g.set(Point(1, 0), "X")
    assert g.get(Point(1, 0)) == "X"
    # Out-of-bounds set is no-op
    g.set(Point(100, 100), "Z")  # should not raise


def test_grid_setitem():
    g = Grid.from_string("abc")
    g[Point(0, 0)] = "Z"
    assert g[Point(0, 0)] == "Z"


def test_grid_find():
    g = Grid.from_string("abc\ndXf")
    p = g.find("X")
    assert p == Point(1, 1)
    assert g.find("Z") is None


def test_grid_find_all():
    g = Grid.from_string("aXb\ncXd")
    pts = g.find_all("X")
    assert len(pts) == 2
    assert Point(1, 0) in pts
    assert Point(1, 1) in pts


def test_grid_iter():
    g = Grid.from_string("ab\ncd")
    cells = list(g)
    assert len(cells) == 4
    assert (Point(0, 0), "a") in cells


def test_grid_copy_independence():
    g = Grid.from_string("abc")
    cp = g.copy()
    cp.set(Point(0, 0), "Z")
    assert g.get(Point(0, 0)) == "a"


def test_grid_str():
    g = Grid.from_string("ab\ncd")
    s = str(g)
    assert "ab" in s
    assert "cd" in s


def test_grid_count():
    g = Grid.from_string("aab\nbaa")
    assert g.count_char("a") == 4
    assert g.count_char("b") == 2
    assert g.count(lambda c: c in "ab") == 6


def test_grid_neighbors4_valid():
    g = Grid.from_string("abc\ndef\nghi")
    # Corner: only 2 neighbors
    ns = g.neighbors4_valid(Point(0, 0))
    assert len(ns) == 2
    # Center: 4 neighbors
    ns = g.neighbors4_valid(Point(1, 1))
    assert len(ns) == 4


def test_grid_neighbors8_valid():
    g = Grid.from_string("abc\ndef\nghi")
    # Corner: only 3 neighbors
    ns = g.neighbors8_valid(Point(0, 0))
    assert len(ns) == 3
    # Center: 8 neighbors
    ns = g.neighbors8_valid(Point(1, 1))
    assert len(ns) == 8
