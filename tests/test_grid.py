# Copyright 2026 Federico De Malmayne Duppa
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the grid_dims layout policy (pure function, no Qt)."""
import pytest

from prompt_library.app import MAX_COLS, MAX_GRID, grid_dims


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, (1, 1)),
        (2, (1, 2)),
        (3, (1, 3)),
        (4, (2, 2)),
        (5, (2, 3)),
        (6, (2, 3)),
        (7, (2, 4)),
        (8, (2, 4)),
        (9, (3, 3)),
        (12, (3, 4)),
        (13, (3, 5)),
        (15, (3, 5)),
        (16, (4, 4)),
        (17, (4, 5)),
        (20, (4, 5)),
        (21, (5, 5)),
        (25, (5, 5)),
    ],
)
def test_known_layouts(n, expected):
    assert grid_dims(n) == expected


def test_perfect_squares_are_square():
    for side in range(2, MAX_COLS + 1):
        assert grid_dims(side * side) == (side, side)


def test_clamped_below_one():
    assert grid_dims(0) == (1, 1)
    assert grid_dims(-5) == (1, 1)


def test_capped_at_max_grid():
    assert grid_dims(MAX_GRID) == (MAX_COLS, MAX_COLS)
    assert grid_dims(100) == (MAX_COLS, MAX_COLS)


def test_invariants_hold_for_every_count():
    for n in range(1, MAX_GRID + 1):
        cols, rows = grid_dims(n)
        assert 1 <= cols <= MAX_COLS
        assert 1 <= rows <= MAX_COLS
        assert cols * rows >= n          # holds all cards
        assert rows >= cols              # vertical (taller than wide)
        assert (cols - 1) * rows < n     # smallest: one fewer column overflows
