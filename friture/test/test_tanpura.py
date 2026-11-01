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

import os
import shutil
import threading
import time
import unittest

import numpy as np

from friture.audiobackend import SAMPLING_RATE
from friture.tanpura import (SAMPLES_DIR, TUNINGS, TUNING_FILES, TARGET_RMS_DB, PEAK_CEILING,
                             GAIN_RAMP_S, STALL_S, Tanpura, make_loop, normalize, playback_ratio,
                             render_drone)


def cents(ratio: float) -> float:
    return 1200 * np.log2(ratio)


class RatioTest(unittest.TestCase):
    def test_shifts_to_the_nearest_octave_of_sa(self):
        c3 = 130.81
        self.assertAlmostEqual(cents(playback_ratio(138.59, c3)), -100, delta=0.5)
        self.assertAlmostEqual(cents(playback_ratio(138.59, c3 * 2)), -100, delta=0.5)  # C4 singer
        self.assertAlmostEqual(cents(playback_ratio(138.59, c3 / 2)), -100, delta=0.5)  # C2 singer

    def test_never_moves_more_than_half_an_octave(self):
        for midi in range(36, 72):
            sa = 440 * 2 ** ((midi - 69) / 12)
            self.assertLessEqual(abs(cents(playback_ratio(139.0, sa))), 600 + 1e-6)

    def test_fine_tune(self):
        self.assertAlmostEqual(cents(playback_ratio(130.81, 130.81, cents=12)), 12, delta=1e-6)


class DroneNotesTest(unittest.TestCase):
    def test_sa_and_first_string_in_every_visible_octave(self):
        t = Tanpura()
        t.set_sa(130.81)
        t.tuning = "pa"
        freqs = t.drone_frequencies(90, 300)
        expected = [98.0, 130.81, 196.0, 261.63]   # Pa2, Sa3, Pa3, Sa4
        self.assertEqual(len(freqs), len(expected))
        for f, e in zip(freqs, expected):
            self.assertAlmostEqual(cents(f / e), 0, delta=2)

    def test_follows_tuning_and_fine_tune(self):
        t = Tanpura()
        t.set_sa(130.81)
        t.tuning, t.cents = "ma", 10
        freqs = t.drone_frequencies(120, 180)      # Sa3 and Ma3 only
        self.assertEqual(len(freqs), 2)
        self.assertAlmostEqual(cents(freqs[0] / 130.81), 10, delta=0.01)
        self.assertAlmostEqual(cents(freqs[1] / 130.81), 510, delta=0.01)


class LoopTest(unittest.TestCase):
    def test_loop_is_continuous_across_the_seam(self):
        t = np.arange(SAMPLING_RATE) / SAMPLING_RATE
        x = np.stack([np.sin(2 * np.pi * 50 * t)] * 2, axis=1)  # 50 whole cycles in a second
        loop = make_loop(x, fade=4800)
        self.assertEqual(len(loop), len(x) - 4800)
        steps = np.abs(np.diff(np.concatenate([loop, loop[:1]]), axis=0))
        self.assertLess(steps.max(), 2 * np.pi * 50 / SAMPLING_RATE * 1.5)

    def test_normalize_hits_the_target_unless_peaks_would_clip(self):
        quiet = np.random.default_rng(0).normal(0, 0.03, (48000, 2))
        rms = np.sqrt(np.mean(normalize(quiet) ** 2))
        self.assertAlmostEqual(20 * np.log10(rms), TARGET_RMS_DB, delta=0.1)
        spiky = quiet.copy()
        spiky[100] = 0.9
        self.assertAlmostEqual(np.abs(normalize(spiky)).max(), PEAK_CEILING, places=5)


class SamplesTest(unittest.TestCase):
    def test_every_tuning_has_its_recording(self):
        for _, _, path, _, _ in TUNINGS:
            self.assertTrue(os.path.exists(os.path.join(SAMPLES_DIR, path)), path)
        self.assertTrue(os.path.exists(os.path.join(SAMPLES_DIR, "CREDITS.txt")))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg")
    def test_rendered_drone_is_shifted_to_sa(self):
        path, recorded_sa, excerpt = TUNING_FILES["ma"]   # a short excerpt
        ratio = playback_ratio(recorded_sa, 130.81)
        loop = render_drone(os.path.join(SAMPLES_DIR, path), ratio, excerpt)
        # the excerpt, stretched by the shift, less the crossfade folded into the loop
        expected = (excerpt[1] - excerpt[0]) / ratio * SAMPLING_RATE - 1.5 * SAMPLING_RATE
        self.assertAlmostEqual(len(loop) / SAMPLING_RATE, expected / SAMPLING_RATE, delta=0.05)
        self.assertEqual(loop.dtype, np.float32)
        self.assertEqual(loop.shape[1], 2)
        # strongest partial near Sa should land on C3 (within a few cents)
        mono = loop.mean(axis=1)
        n = 1 << int(np.log2(len(mono)))
        spec = np.abs(np.fft.rfft(mono[:n] * np.hanning(n)))
        freqs = np.fft.rfftfreq(n, 1 / SAMPLING_RATE)
        band = (freqs > 120) & (freqs < 145)
        peak = freqs[band][np.argmax(spec[band])]
        self.assertLess(abs(cents(peak / 130.81)), 8)


class PlaybackTest(unittest.TestCase):
    def make(self) -> Tanpura:
        t = Tanpura()
        t._loop = np.ones((1000, 2), dtype=np.float32)
        t._stream = object()   # rendering only; nothing is opened
        return t

    def test_fades_in_to_the_volume(self):
        t = self.make()
        t.set_volume(50)
        ramp = int(GAIN_RAMP_S * SAMPLING_RATE)
        out = np.concatenate([t.render(512) for _ in range(ramp // 512 + 4)])
        self.assertEqual(out[0, 0], 0.0)
        self.assertTrue(np.all(np.diff(out[:ramp, 0]) >= 0))
        self.assertAlmostEqual(out[-1, 0], 0.5, places=5)

    def test_loops_through_the_buffer(self):
        t = self.make()
        t._loop = np.arange(10, dtype=np.float32)[:, None].repeat(2, axis=1)
        t._gain = 1.0
        t.set_volume(100)
        np.testing.assert_allclose(t.render(25)[:, 0], np.arange(25) % 10)

    def test_switching_loops_crossfades(self):
        t = self.make()
        t._gain, t.volume = 1.0, 100
        t.render(100)
        with t._lock:
            t._old, t._switch = (t._loop, t._pos), 0
            t._loop, t._pos = np.zeros((1000, 2), dtype=np.float32), 0
        out = np.concatenate([t.render(4800) for _ in range(5)])[:, 0]
        self.assertAlmostEqual(out[0], 1.0, places=3)        # starts on the old loop
        self.assertTrue(np.all(np.diff(out) <= 1e-6))         # fades smoothly
        self.assertEqual(out[-1], 0.0)                        # ends on the new one
        self.assertIsNone(t._old)


class FakeStream:
    active = True
    latency = 0.0

    def __init__(self):
        self.closed = threading.Event()

    def stop(self):
        pass

    def close(self):
        self.closed.set()


class OutputRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.opened = []
        self._open = Tanpura._open_stream
        test = self

        def fake_open(t):
            t._stream_id += 1
            t._opened_at = t._last_callback = time.monotonic()
            t._stream = FakeStream()
            test.opened.append(t._stream)

        Tanpura._open_stream = fake_open

    def tearDown(self):
        Tanpura._open_stream = self._open

    def make(self) -> Tanpura:
        t = Tanpura()
        t._wanted = True
        t._loop = np.ones((1000, 2), dtype=np.float32)
        return t

    def test_reopens_an_output_that_stopped_asking_for_audio(self):
        t = self.make()
        t._apply_output(None)
        first = t._stream
        t._apply_output(None)                       # healthy: left alone
        self.assertIs(t._stream, first)
        t._opened_at = t._last_callback = time.monotonic() - STALL_S - 1
        t._apply_output(None)                       # stalled: replaced
        self.assertIsNot(t._stream, first)
        self.assertTrue(first.closed.wait(2))       # closed in the background

    def test_holds_the_stream_closed_while_the_speaker_is_missing(self):
        t = self.make()
        t.output_device = "pulse:jbl"
        t._apply_output({"jbl"})
        self.assertIsNotNone(t._stream)
        t._apply_output({"headphones"})
        self.assertIsNone(t._stream)
        t._apply_output({"jbl", "headphones"})
        self.assertIsNotNone(t._stream)

    def test_an_old_stream_plays_silence_once_a_new_one_is_open(self):
        t = self.make()
        t._gain, t.volume = 1.0, 100
        out = np.empty((64, 2), dtype=np.float32)
        t._callback(t._stream_id, out, 64, None, None)
        self.assertTrue(np.all(out == 1.0))
        t._callback(t._stream_id - 1, out, 64, None, None)
        self.assertTrue(np.all(out == 0.0))


if __name__ == '__main__':
    unittest.main()
