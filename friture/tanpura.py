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

"""Tanpura drone for the pitch tracker: recordings of an acoustic tanpura,
looped and shifted to the chosen Sa, played on an output of its own so the
drone can fill the room from a speaker while the song, metronome and voice
monitor stay in the singer's headphones.

The recordings are credited in tanpura_samples/CREDITS.txt (CC BY 4.0).
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from friture.audiobackend import SAMPLING_RATE
from friture.plotting.frequency_scales import midi_to_frequency

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tanpura_samples")

# (label, key, file, Sa of the recording in Hz, (start, end) seconds used).
# The Sa values were measured from the recordings (spectral peaks of Sa and its
# octaves); all sit near C#3. The excerpts leave out people talking in the
# room, found with a vocal separation pass (Demucs) over each recording.
TUNINGS: List[Tuple[str, str, str, float, Tuple[float, float]]] = [
    ("Pa", "pa", "153263.flac", 139.0, (0.0, 34.5)),
    ("Ma", "ma", "153267.flac", 139.3, (0.0, 16.0)),
    ("Ni", "ni", "153264.flac", 138.8, (53.0, 70.0)),
    ("Dha", "dha", "153266.flac", 138.6, (0.0, 10.1)),
]
TUNING_FILES = {key: (path, sa, excerpt) for _, key, path, sa, excerpt in TUNINGS}
# semitones above Sa of the first string's note; the other strings are Sa
FIRST_STRING = {"pa": 7, "ma": 5, "ni": 11, "dha": 9}

DEFAULT_TUNING = "pa"
DEFAULT_VOLUME = 70        # percent
FINE_TUNE_RANGE = (-50, 50)  # cents

LOOP_FADE_S = 1.5          # crossfade folding the end of a recording onto its start
TARGET_RMS_DB = -16.0      # the recordings sit near -24 dBFS
PEAK_CEILING = 0.95
SWITCH_FADE_S = 0.4        # crossfade when the Sa or tuning changes mid-drone
GAIN_RAMP_S = 0.25         # fade in/out on start, stop and volume changes
WATCH_INTERVAL_MS = 2000   # how often to check that the chosen speaker is still there
STALL_S = 3.0              # the output stopped asking for audio this long ago: reopen it


def playback_ratio(recorded_sa: float, sa_hz: float, cents: float = 0.0) -> float:
    """Resampling ratio that moves the recording's Sa onto the octave of `sa_hz`
    nearest to it, so a C#3 tanpura plays at C3 for a C3 or C4 singer alike
    instead of being dragged a whole octave."""
    target = sa_hz * 2.0 ** (cents / 1200.0)
    while target / recorded_sa > 2 ** 0.5:
        target /= 2.0
    while recorded_sa / target > 2 ** 0.5:
        target *= 2.0
    return target / recorded_sa


def make_loop(x: np.ndarray, fade: int) -> np.ndarray:
    """Fold the last `fade` frames over the start with an equal-power
    crossfade, so the loop flows from its end into its beginning."""
    fade = min(fade, len(x) // 4)
    length = len(x) - fade
    out = x[:length].copy()
    t = (np.arange(fade) / fade)[:, None]
    out[:fade] = x[:fade] * np.sin(t * np.pi / 2) + x[length:] * np.cos(t * np.pi / 2)
    return out


def normalize(x: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x ** 2)))
    peak = float(np.max(np.abs(x)))
    if rms == 0.0:
        return x
    return x * min(10 ** (TARGET_RMS_DB / 20) / rms, PEAK_CEILING / peak)


def render_drone(path: str, ratio: float, excerpt: Tuple[float, float]) -> np.ndarray:
    """Decode the `excerpt` (start, end seconds) of a recording, shift it by `ratio` (by resampling, which keeps the
    instrument's timbre and changes the plucking pace by the same ratio) and
    return a normalised stereo loop at SAMPLING_RATE, float32 (frames, 2)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found; install it to play the tanpura")
    rate = int(subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "a:0",
                               "-show_entries", "stream=sample_rate", "-of", "csv=p=0", path],
                              capture_output=True, check=True, text=True).stdout.strip())
    start, end = excerpt
    cmd = [ffmpeg, "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", path,
           "-filter:a", f"asetrate={rate * ratio:.3f},aresample={SAMPLING_RATE}",
           "-ac", "2", "-f", "f32le", "-"]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    x = np.frombuffer(result.stdout, dtype=np.float32).reshape(-1, 2)
    return normalize(make_loop(x, int(LOOP_FADE_S * SAMPLING_RATE))).astype(np.float32)


def available_sinks() -> Optional[set]:
    """PulseAudio / PipeWire sink names, or None when they can't be listed."""
    if shutil.which("pactl") is None:
        return None
    try:
        out = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True,
                             check=True, timeout=3, text=True).stdout
    except Exception:
        return None
    return {line.split("\t")[1] for line in out.splitlines() if "\t" in line}


class Tanpura(QObject):
    """Looping tanpura drone on its own output stream.

    Rendering (decode, shift, loop, normalise) runs on a worker thread; the
    audio callback only reads the current loop and crossfades into a new one
    when the Sa, fine-tune or tuning changes.
    """

    state_changed = pyqtSignal(str)   # status text for the settings dialog
    running_changed = pyqtSignal(bool)
    _rendered = pyqtSignal(int, object)  # generation, loop (or exception)
    _sinks_listed = pyqtSignal(object)   # set of sink names, or None

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.tuning = DEFAULT_TUNING
        self.sa_hz = midi_to_frequency(48)
        self.cents = 0
        self.volume = DEFAULT_VOLUME
        self.output_device = ""

        self._wanted = False                  # the user switched it on
        self._stream = None
        self._lock = threading.Lock()
        self._loop: Optional[np.ndarray] = None
        self._pos = 0
        self._old: Optional[Tuple[np.ndarray, int]] = None  # loop being faded out, position
        self._switch = 0                      # frames into the switch crossfade
        self._gain = 0.0                      # current gain, ramped towards the target
        self._stopping = False
        self._cache: Dict[Tuple[str, float], np.ndarray] = {}
        self._generation = 0
        self._rendered.connect(self._on_rendered)
        self._stream_id = 0                   # callbacks of older streams play silence
        self._last_callback = 0.0
        self._opened_at = 0.0
        self._listing = False
        self._sinks_listed.connect(self._apply_output)

        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_INTERVAL_MS)
        self._watch.timeout.connect(self._check_output)

    # ---- settings --------------------------------------------------------

    def set_tuning(self, key: str) -> None:
        if key != self.tuning:
            self.tuning = key
            self._prepare()

    def set_sa(self, sa_hz: float) -> None:
        if sa_hz != self.sa_hz:
            self.sa_hz = sa_hz
            self._prepare()

    def set_cents(self, cents: int) -> None:
        if cents != self.cents:
            self.cents = cents
            self._prepare()

    def set_volume(self, percent: int) -> None:
        self.volume = percent

    def set_output_device(self, key: str) -> None:
        if key == self.output_device:
            return
        self.output_device = key
        if self._stream is not None:
            self._close_stream()
            self._check_output()

    def drone_frequencies(self, low: float, high: float) -> List[float]:
        """Frequencies of the drone's notes (Sa and the first string's note, as
        tuned, fine-tune included) in every octave between low and high Hz."""
        sa = self.sa_hz * 2.0 ** (self.cents / 1200.0)
        freqs = []
        for semitones in (0, FIRST_STRING[self.tuning]):
            f = sa * 2.0 ** (semitones / 12.0)
            while f > low:
                f /= 2.0
            while f <= high:
                if f >= low:
                    freqs.append(f)
                f *= 2.0
        return sorted(freqs)

    # ---- on / off ----------------------------------------------------------

    def is_on(self) -> bool:
        return self._wanted

    def start(self) -> None:
        if self._wanted:
            return
        self._wanted = True
        self._watch.start()
        self._prepare()

    def stop(self) -> None:
        self._wanted = False
        self._watch.stop()
        self._close_stream()
        self.state_changed.emit("")
        self.running_changed.emit(False)

    # ---- rendering -------------------------------------------------------

    def _ratio(self) -> float:
        _, recorded_sa, _ = TUNING_FILES[self.tuning]
        return playback_ratio(recorded_sa, self.sa_hz, self.cents)

    def _prepare(self) -> None:
        """Render the loop for the current settings (cached), then play it."""
        if not self._wanted:
            return
        self._generation += 1
        generation = self._generation
        key = (self.tuning, round(self._ratio(), 6))
        if key in self._cache:
            self._on_rendered(generation, self._cache[key])
            return
        self.state_changed.emit("preparing…")
        file, _, excerpt = TUNING_FILES[self.tuning]
        path = os.path.join(SAMPLES_DIR, file)
        ratio = self._ratio()

        def work() -> None:
            try:
                loop = render_drone(path, ratio, excerpt)
                self._cache[key] = loop
                self._rendered.emit(generation, loop)
            except Exception as e:
                self.logger.exception("could not prepare the tanpura")
                self._rendered.emit(generation, e)

        threading.Thread(target=work, name="tanpura-render", daemon=True).start()

    def _on_rendered(self, generation: int, loop: object) -> None:
        if generation != self._generation or not self._wanted:
            return  # superseded by a newer setting, or switched off meanwhile
        if isinstance(loop, Exception):
            self.state_changed.emit(f"failed: {loop}")
            return
        with self._lock:
            if self._loop is not None and self._stream is not None:
                self._old = (self._loop, self._pos)
                self._switch = 0
            self._loop, self._pos = loop, 0
        self._check_output()

    # ---- output ----------------------------------------------------------

    def _target_sink(self) -> Optional[str]:
        key = self.output_device
        return key[len("pulse:"):] if key.startswith("pulse:") else None

    def _check_output(self) -> None:
        """Keep the stream on the chosen speaker: hold it closed while that
        speaker is missing (rather than letting the sound server move the drone
        into the headphones), reopen it when the speaker comes back, and reopen
        it if it stops asking for audio (a Bluetooth link that failed)."""
        if not self._wanted or self._loop is None:
            return
        if self._target_sink() is None:
            self._apply_output(None)
        elif not self._listing:
            # pactl can stall while a Bluetooth device misbehaves: list off the GUI thread
            self._listing = True

            def work() -> None:
                sinks = available_sinks()
                self._listing = False
                self._sinks_listed.emit(sinks)

            threading.Thread(target=work, name="tanpura-sinks", daemon=True).start()

    def _apply_output(self, sinks: Optional[set]) -> None:
        if not self._wanted or self._loop is None:
            return
        sink = self._target_sink()
        present = sink is None or sinks is None or sink in sinks
        if not present:
            if self._stream is not None:
                self._close_stream()
            self.state_changed.emit("waiting for the speaker…")
            return
        now = time.monotonic()
        if (self._stream is not None and now - self._opened_at > STALL_S
                and now - self._last_callback > STALL_S):
            self.logger.warning("the tanpura output stopped for %.1f s; reopening it",
                                now - self._last_callback)
            self._close_stream()
        if self._stream is None:
            self._open_stream()
        elif self._stream.active:
            self.state_changed.emit("playing")

    def _open_stream(self) -> None:
        from friture.reference_track import open_output_stream
        with self._lock:
            self._gain = 0.0
            self._stopping = False
        self._stream_id += 1
        stream_id = self._stream_id
        self._opened_at = self._last_callback = time.monotonic()
        try:
            self._stream = open_output_stream(self.output_device, self.logger,
                                              samplerate=SAMPLING_RATE, channels=2, dtype="float32",
                                              callback=lambda *args: self._callback(stream_id, *args))
        except Exception as e:
            self.logger.exception("could not open the tanpura output")
            self.state_changed.emit(f"could not open the output: {e}")
            return
        self.state_changed.emit("playing")
        self.running_changed.emit(True)

    def _close_stream(self) -> None:
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        # let the callback ramp down before the stream goes, so it ends without a
        # click; off the GUI thread, since closing a stream on a failed Bluetooth
        # link can block
        with self._lock:
            self._stopping = True
            self._old = None

        def close() -> None:
            try:
                if stream.active:
                    time.sleep(GAIN_RAMP_S + float(stream.latency))
                stream.stop()
                stream.close()
            except Exception:
                self.logger.exception("error stopping the tanpura")

        threading.Thread(target=close, name="tanpura-close", daemon=True).start()

    # ---- audio thread ----------------------------------------------------

    def _read(self, loop: np.ndarray, pos: int, frames: int) -> Tuple[np.ndarray, int]:
        idx = (pos + np.arange(frames)) % len(loop)
        return loop[idx], (pos + frames) % len(loop)

    def _callback(self, stream_id: int, out_data: np.ndarray, frames: int, time_info, status) -> None:
        if stream_id != self._stream_id:
            out_data.fill(0)  # a stream being closed after a newer one opened
            return
        self._last_callback = time.monotonic()
        out_data[:] = self.render(frames)

    def render(self, frames: int) -> np.ndarray:
        with self._lock:
            if self._loop is None:
                return np.zeros((frames, 2), dtype=np.float32)
            block, self._pos = self._read(self._loop, self._pos, frames)

            if self._old is not None:
                switch = int(SWITCH_FADE_S * SAMPLING_RATE)
                old_block, old_pos = self._read(self._old[0], self._old[1], frames)
                t = np.clip((self._switch + np.arange(frames)) / switch, 0.0, 1.0)[:, None]
                block = block * np.sin(t * np.pi / 2) + old_block * np.cos(t * np.pi / 2)
                self._switch += frames
                self._old = None if self._switch >= switch else (self._old[0], old_pos)

            target = 0.0 if self._stopping else self.volume / 100.0
            step = frames / (GAIN_RAMP_S * SAMPLING_RATE)
            end = self._gain + float(np.clip(target - self._gain, -step, step))
            gains = np.linspace(self._gain, end, frames, endpoint=False, dtype=np.float32)[:, None]
            self._gain = end
            return (block * gains).astype(np.float32)
