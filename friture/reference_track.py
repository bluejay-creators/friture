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

"""Reference track for the pitch tracker: decode an audio file, run the same
pitch estimator over it offline, and play it back while exposing its pitch
curve on the live timeline so a singer can compare against it."""

import logging
import math
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from sounddevice import OutputStream, CallbackStop

from friture.audiobackend import SAMPLING_RATE
from friture.ringbuffer import RingBuffer


def find_ffmpeg() -> Optional[str]:
    """ffmpeg from PATH, else the usual package-manager locations — a bundled
    .app launched from Finder/Dock does not inherit the shell's PATH."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    home = os.path.expanduser("~")
    for candidate in (f"{home}/.nix-profile/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg",
                      "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def decode_audio(path: str, sample_rate: int = SAMPLING_RATE) -> np.ndarray:
    """Decode any ffmpeg-readable file to float32 mono at sample_rate."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found; install it to decode reference files")
    cmd = [ffmpeg, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-"]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    return np.frombuffer(result.stdout, dtype=np.float32)


class ReferenceTrack(QObject):
    """Owns the decoded audio, its pitch estimates, and playback.

    Pitch estimates are one value per tracker step (fft_size * (1 - overlap)
    samples), NaN where unvoiced — the same representation the live tracker
    produces, so both curves can be drawn by the same code.
    """

    loaded = pyqtSignal(str)          # status text
    load_failed = pyqtSignal(str)     # error text
    playing_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.path: Optional[str] = None
        self.samples: Optional[np.ndarray] = None
        self.pitches: Optional[np.ndarray] = None
        self.step = 1
        self.transpose_semitones = 0
        self._thread: Optional[threading.Thread] = None
        self._generation = 0

        self._stream: Optional[OutputStream] = None
        self._play_pos = 0                   # samples handed to the output so far
        self._start_monotonic: Optional[float] = None
        self._lock = threading.Lock()

    # ---- loading -------------------------------------------------------

    def load(self, path: str, make_tracker) -> None:
        """Decode and analyse `path` on a worker thread.

        `make_tracker(input_buf)` must return a PitchTracker configured like the
        live one, so the reference is judged by the same rules.
        """
        self.stop()
        self.path = path
        self.samples = None
        self.pitches = None
        self._generation += 1
        generation = self._generation

        def work() -> None:
            try:
                samples = decode_audio(path)
                tracker = make_tracker(RingBuffer())
                step = math.floor(tracker.fft_size * (1.0 - tracker.overlap))
                estimates = []
                chunk = SAMPLING_RATE  # one second at a time keeps the ring buffer small
                for start in range(0, samples.size, chunk):
                    tracker.input_buf.push(samples[np.newaxis, start:start + chunk], 0.0)
                    estimates.extend(tracker.estimate_pitch(f) for f in tracker.new_frames())
                pitches = np.array(estimates, dtype=np.float64)
            except Exception as e:  # noqa: BLE001 - reported to the UI
                self.logger.exception("reference load failed")
                if generation == self._generation:
                    self.load_failed.emit(str(e))
                return
            if generation != self._generation:
                return  # superseded by a newer load
            with self._lock:
                self.samples = samples
                self.pitches = pitches
                self.step = step
            voiced = int(np.isfinite(pitches).sum())
            self.loaded.emit(f"{samples.size / SAMPLING_RATE:.0f} s, {voiced * step / SAMPLING_RATE:.0f} s voiced")

        self._thread = threading.Thread(target=work, name="reference-track-load", daemon=True)
        self._thread.start()

    def clear(self) -> None:
        self.stop()
        self._generation += 1
        self.path = None
        with self._lock:
            self.samples = None
            self.pitches = None
        self._start_monotonic = None
        self._play_pos = 0

    def is_loaded(self) -> bool:
        return self.pitches is not None

    # ---- playback ------------------------------------------------------

    def is_playing(self) -> bool:
        return self._stream is not None

    def play(self) -> None:
        if self.samples is None or self._stream is not None:
            return
        self._play_pos = 0
        self._start_monotonic = time.monotonic()
        try:
            self._stream = OutputStream(samplerate=SAMPLING_RATE, channels=1, dtype="float32",
                                        callback=self._callback, finished_callback=self._on_finished)
            self._stream.start()
        except Exception:
            self.logger.exception("could not open output stream for the reference track")
            self._stream = None
            return
        self.playing_changed.emit(True)

    def stop(self) -> None:
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        try:
            stream.stop()
            stream.close()
        except Exception:
            self.logger.exception("error stopping reference playback")
        self.playing_changed.emit(False)

    def _callback(self, out_data: np.ndarray, frames: int, time_info, status) -> None:
        samples = self.samples
        if samples is None:
            out_data.fill(0)
            raise CallbackStop()
        start = self._play_pos
        end = min(start + frames, samples.size)
        n = end - start
        out_data[:n, 0] = samples[start:end]
        if n < frames:
            out_data[n:, 0] = 0
        self._play_pos = end
        if end >= samples.size:
            raise CallbackStop()

    def _on_finished(self) -> None:
        # called from the audio thread when the stream drains; hand off to Qt
        if self._stream is not None:
            self._stream = None
            self.playing_changed.emit(False)

    # ---- display -------------------------------------------------------

    def window(self, now_monotonic: float, duration: float, n: int) -> Optional[np.ndarray]:
        """Reference pitches (Hz, NaN = gap) for `n` display frames ending now and
        spanning `duration` seconds, on the same wall-clock timeline as the live
        curve. Only the part that has actually been played is shown, so after
        stop the curve keeps scrolling off with the live history."""
        with self._lock:
            pitches = self.pitches
            step = self.step
        if pitches is None or self._start_monotonic is None:
            return None
        played_frames = self._play_pos // step
        if played_frames <= 0:
            return None
        t = now_monotonic - duration + np.linspace(0.0, duration, n) - self._start_monotonic
        idx = np.rint(t * SAMPLING_RATE / step).astype(np.int64)
        valid = (idx >= 0) & (idx < min(played_frames, pitches.size))
        out = np.full(n, np.nan)
        out[valid] = pitches[idx[valid]]
        if self.transpose_semitones:
            out *= 2.0 ** (self.transpose_semitones / 12.0)
        return out
