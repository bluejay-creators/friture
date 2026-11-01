# -*- coding: utf-8 -*-

# This file is part of Friture.
#
# Friture is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation.
#
# Friture is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Friture.  If not, see <http://www.gnu.org/licenses/>.

import unittest
import numpy as np

from friture.audiobackend import SAMPLING_RATE
from friture.metronome import (Metronome, TAAL_BEATS, SAM, TALI, KHALI, PLAIN,
                               CLICKS, LINE_COLORS)


def render_seconds(metronome: Metronome, seconds: float, block: int = 512) -> np.ndarray:
    frames = int(seconds * SAMPLING_RATE)
    return np.concatenate([metronome.render(min(block, frames - i)) for i in range(0, frames, block)])


class TaalTest(unittest.TestCase):
    def test_teentaal_marks(self):
        beats = TAAL_BEATS["teentaal"]
        self.assertEqual(len(beats), 16)
        self.assertEqual(beats[0], SAM)
        self.assertEqual(beats[4], TALI)
        self.assertEqual(beats[8], KHALI)
        self.assertEqual(beats[12], TALI)
        self.assertEqual(beats.count(PLAIN), 12)

    def test_cycle_lengths(self):
        expected = {"teentaal": 16, "ektaal": 12, "jhaptaal": 10, "keherwa": 8,
                    "rupak": 7, "dadra": 6, "click": 4}
        self.assertEqual({k: len(v) for k, v in TAAL_BEATS.items()}, expected)


class SchedulingTest(unittest.TestCase):
    def test_beats_fall_on_the_grid_across_blocks(self):
        m = Metronome()
        m.set_bpm(120)
        render_seconds(m, 2.0, block=333)  # block size unrelated to the beat period
        self.assertEqual([at for at, _ in m._history],
                         [i * SAMPLING_RATE // 2 for i in range(4)])

    def test_click_is_rendered_at_each_beat(self):
        m = Metronome()
        m.set_bpm(60)
        out = render_seconds(m, 2.0)
        click = CLICKS[SAM].size
        gain = m.volume / 100.0
        np.testing.assert_allclose(out[:click], gain * CLICKS[SAM], atol=1e-6)
        np.testing.assert_allclose(out[SAMPLING_RATE:SAMPLING_RATE + click], gain * CLICKS[PLAIN], atol=1e-6)
        self.assertEqual(np.abs(out[click:SAMPLING_RATE]).max(), 0.0)

    def test_teentaal_cycle_wraps_to_sam(self):
        m = Metronome()
        m.set_bpm(480)
        render_seconds(m, 17 * 60 / 480)
        kinds = [kind for _, kind in m._history]
        self.assertEqual(kinds[:16], TAAL_BEATS["teentaal"])
        self.assertEqual(kinds[16], SAM)

    def test_tempo_change_applies_from_the_next_beat(self):
        m = Metronome()
        m.set_bpm(60)
        render_seconds(m, 0.5)    # beat 0 at 0, beat 1 scheduled for 1.0 s
        m.set_bpm(120)
        render_seconds(m, 1.6)
        self.assertEqual([at for at, _ in m._history][:3],
                         [0, SAMPLING_RATE, SAMPLING_RATE + SAMPLING_RATE // 2])

    def test_taal_change_restarts_at_sam(self):
        m = Metronome()
        m.set_bpm(240)
        render_seconds(m, 0.6)    # three beats of teentaal
        m.set_taal("dadra")
        render_seconds(m, 0.25)
        self.assertEqual(m._history[-1][1], SAM)

    def test_volume_scales_the_click(self):
        m = Metronome()
        m.set_volume(0)
        self.assertEqual(np.abs(render_seconds(m, 1.0)).max(), 0.0)


    def test_sound_off_is_silent_but_keeps_the_beats(self):
        m = Metronome()
        m.set_bpm(120)
        m.set_sound(False)
        self.assertEqual(np.abs(render_seconds(m, 1.1)).max(), 0.0)
        self.assertEqual(len(m._history), 3)


class BeatLinesTest(unittest.TestCase):
    def test_none_before_start(self):
        self.assertIsNone(Metronome().beat_lines(0.0, 10.0))

    def test_lines_are_placed_on_the_timeline(self):
        m = Metronome()
        m.set_bpm(60)
        m._t0 = 100.0
        render_seconds(m, 2.5)    # beats at t0, t0 + 1, t0 + 2
        x, y, colors = m.beat_lines(now_monotonic=102.5, duration=5.0)

        # sam: one full-height segment; plain beats: two short edge ticks each
        self.assertEqual(x.size, 3 + 6 + 6)
        self.assertAlmostEqual(x[0], (100.0 - 97.5) / 5.0)
        self.assertEqual((y[0], y[1]), (0.0, 1.0))
        self.assertAlmostEqual(x[3], (101.0 - 97.5) / 5.0)
        self.assertTrue(np.isnan(x[2]) and np.isnan(y[2]))
        self.assertEqual(tuple(colors[0]), LINE_COLORS[SAM])
        self.assertEqual(colors.shape, (x.size, 4))

    def test_beats_outside_the_window_are_dropped(self):
        m = Metronome()
        m.set_bpm(60)
        m._t0 = 100.0
        render_seconds(m, 2.5)
        x, _, _ = m.beat_lines(now_monotonic=110.5, duration=9.0)  # window 101.5 .. 110.5
        finite = x[np.isfinite(x)]
        self.assertTrue(np.allclose(finite, (102.0 - 101.5) / 9.0))


if __name__ == '__main__':
    unittest.main()
