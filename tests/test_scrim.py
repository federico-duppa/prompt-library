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
"""Tests for the animated-scrim logic (pure geometry, no Qt painting)."""
from prompt_library.app import Meteor, make_starfield, spawn_meteor


def test_meteor_advances_by_velocity():
    m = Meteor(0.0, 0.0, 3.0, 4.0, length=100, life=10)
    m.advance()
    assert (m.x, m.y, m.age) == (3.0, 4.0, 1)


def test_meteor_is_done_after_its_lifetime():
    m = Meteor(0.0, 0.0, 1.0, 1.0, length=50, life=5)
    for _ in range(5):
        assert not m.done
        m.advance()
    assert m.done


def test_meteor_alpha_fades_in_then_out():
    m = Meteor(0.0, 0.0, 1.0, 1.0, length=50, life=40)
    assert m.alpha() == 0.0          # invisible at birth
    for _ in range(8):
        m.advance()
    assert m.alpha() == 1.0          # fully visible mid-life
    while m.age < 39:
        m.advance()
    assert 0.0 < m.alpha() < 1.0     # fading out near the end


def test_spawn_meteor_enters_moving_downward():
    for _ in range(100):
        m = spawn_meteor(1920, 1080)
        assert m.vy > 0              # travels down the screen
        assert m.length > 0
        assert m.life > 0


def test_make_starfield_count_and_bounds():
    stars = make_starfield(800, 600, n=60)
    assert len(stars) == 60
    assert all(0 <= s.x <= 800 and 0 <= s.y <= 600 for s in stars)
    assert all(s.r > 0 and 0 <= s.alpha <= 255 for s in stars)
