#!/usr/bin/env python
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

"""Taal metronome for the pitch tracker: clicks through the same output as
the reference track, with sam, tali and khali voiced differently, and the
beats exposed on the live timeline so a singer can see where they land.

Beats are scheduled by sample count inside the audio callback, so the clicks
are sample-accurate whatever the GUI thread is doing; the display maps those
sample positions back to wall-clock time.
"""

import collections
import logging
import threading
import time
from typing import Deque, List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from sounddevice import OutputStream

from friture.audiobackend import SAMPLING_RATE

SAM, TALI, KHALI, PLAIN = "sam", "tali", "khali", "plain"


def _taal(vibhags: List[int], marks: List[str]) -> List[str]:
    """Beat kinds for one cycle: each vibhag opens with its mark (sam, tali or
    khali), the rest of its beats are plain."""
    beats: List[str] = []
    for size, mark in zip(vibhags, marks):
        beats += [mark] + [PLAIN] * (size - 1)
    return beats


# (label, key, beat kinds for one cycle)
TAALS: List[Tuple[str, str, List[str]]] = [
    ("Teentaal (16)", "teentaal", _taal([4, 4, 4, 4], [SAM, TALI, KHALI, TALI])),
    ("Ektaal (12)", "ektaal", _taal([2, 2, 2, 2, 2, 2], [SAM, KHALI, TALI, KHALI, TALI, TALI])),
    ("Jhaptaal (10)", "jhaptaal", _taal([2, 3, 2, 3], [SAM, TALI, KHALI, TALI])),
    ("Keherwa (8)", "keherwa", _taal([4, 4], [SAM, KHALI])),
    ("Rupak (7)", "rupak", _taal([3, 2, 2], [SAM, TALI, TALI])),
    ("Dadra (6)", "dadra", _taal([3, 3], [SAM, KHALI])),
    ("Click (4)", "click", _taal([4], [SAM])),
]
TAAL_BEATS = {key: beats for _, key, beats in TAALS}

DEFAULT_TAAL = "teentaal"
DEFAULT_BPM = 60
BPM_RANGE = (10, 480)   # vilambit ektaal sits near 15, drut teentaal well past 300
DEFAULT_VOLUME = 60     # percent


def _click(freq: float, gain: float, decay_s: float = 0.018, length_s: float = 0.08) -> np.ndarray:
    t = np.arange(int(length_s * SAMPLING_RATE)) / SAMPLING_RATE
    # 1 ms attack so the click starts without a pop
    envelope = np.minimum(t / 0.001, 1.0) * np.exp(-t / decay_s)
    return (gain * envelope * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# Sam rings highest and loudest, khali is the low, soft "empty" beat.
CLICKS = {
    SAM: _click(1760.0, 0.9, decay_s=0.03),
    TALI: _click(1175.0, 0.6),
    KHALI: _click(660.0, 0.45),
    PLAIN: _click(1175.0, 0.3),
}

# Timeline styling: vibhag beats get a full-height line, plain beats a short
# tick at the top and bottom edges so the grid stays readable at fast tempi.
LINE_COLORS = {
    SAM: (192, 57, 43, 255),     # same red as Sa
    TALI: (128, 128, 128, 255),
    KHALI: (90, 143, 208, 255),
    PLAIN: (128, 128, 128, 255),
}
TICK_HEIGHT = 0.05


class Metronome(QObject):
    running_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.bpm = DEFAULT_BPM
        self.taal = DEFAULT_TAAL
        self.volume = DEFAULT_VOLUME
        self.sound = True       # off: silent clicks, beats still drawn on the timeline
        self.output_device = ""

        self._stream: Optional[OutputStream] = None
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self._pos = 0                        # samples rendered so far
        self._next_beat = 0.0                # sample position of the next beat
        self._beat = 0                       # index into the taal cycle
        self._sounding: List[Tuple[int, np.ndarray]] = []
        # (sample position, kind) of beats already scheduled, for the display
        self._history: Deque[Tuple[int, str]] = collections.deque(maxlen=4096)
        self._t0: Optional[float] = None     # monotonic time of sample 0 at the speaker

    # ---- settings --------------------------------------------------------

    def set_bpm(self, bpm: int) -> None:
        self.bpm = bpm  # takes effect from the next beat

    def set_taal(self, taal: str) -> None:
        if taal != self.taal:
            self.taal = taal
            self._beat = 0  # the next beat is sam of the new taal

    def set_volume(self, percent: int) -> None:
        self.volume = percent

    def set_sound(self, on: bool) -> None:
        self.sound = on

    def set_output_device(self, key: str) -> None:
        if key == self.output_device:
            return
        self.output_device = key
        if self.is_running():
            self.stop()
            self.start()

    # ---- playback --------------------------------------------------------

    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        from friture.reference_track import open_output_stream
        with self._lock:
            self._reset()
        try:
            stream = open_output_stream(self.output_device, self.logger,
                                        samplerate=SAMPLING_RATE, channels=1, dtype="float32",
                                        callback=self._callback)
        except Exception:
            self.logger.exception("could not open output stream for the metronome")
            return
        # sample 0 reaches the speaker one output latency after the stream starts
        self._t0 = time.monotonic() + float(stream.latency)
        self._stream = stream
        self.running_changed.emit(True)

    def stop(self) -> None:
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        try:
            stream.stop()
            stream.close()
        except Exception:
            self.logger.exception("error stopping the metronome")
        self.running_changed.emit(False)

    def _callback(self, out_data: np.ndarray, frames: int, time_info, status) -> None:
        out_data[:, 0] = self.render(frames)

    def render(self, frames: int) -> np.ndarray:
        """The next `frames` samples of clicks, scheduling beats as they fall due."""
        out = np.zeros(frames, dtype=np.float32)
        with self._lock:
            start, end = self._pos, self._pos + frames
            while self._next_beat < end:
                beats = TAAL_BEATS[self.taal]
                kind = beats[self._beat % len(beats)]
                at = int(round(self._next_beat))
                self._sounding.append((at, CLICKS[kind]))
                self._history.append((at, kind))
                self._beat = (self._beat + 1) % len(beats)
                self._next_beat += SAMPLING_RATE * 60.0 / self.bpm

            gain = self.volume / 100.0 if self.sound else 0.0
            for at, click in self._sounding:
                a, b = max(at, start), min(at + click.size, end)
                if a < b:
                    out[a - start:b - start] += gain * click[a - at:b - at]
            self._sounding = [(at, c) for at, c in self._sounding if at + c.size > end]
            self._pos = end
        return out

    # ---- display ---------------------------------------------------------

    def beat_lines(self, now_monotonic: float, duration: float
                   ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Vertical beat markers for a timeline spanning `duration` seconds and
        ending now, as (x, y, rgba) in the plot's 0..1 coordinates with NaN
        separators between segments; None when nothing is to be drawn."""
        if self._t0 is None:
            return None
        with self._lock:
            history = list(self._history)
        xs: List[float] = []
        ys: List[float] = []
        colors: List[Tuple[int, int, int, int]] = []
        nan = float("nan")
        for at, kind in history:
            x = (self._t0 + at / SAMPLING_RATE - (now_monotonic - duration)) / duration
            if not 0.0 <= x <= 1.0:
                continue
            if kind == PLAIN:
                segments = [(0.0, TICK_HEIGHT), (1.0 - TICK_HEIGHT, 1.0)]
            else:
                segments = [(0.0, 1.0)]
            for y0, y1 in segments:
                xs += [x, x, nan]
                ys += [y0, y1, nan]
                colors += [LINE_COLORS[kind]] * 3
        if not xs:
            return None
        return np.array(xs), np.array(ys), np.array(colors, dtype=np.uint8)
