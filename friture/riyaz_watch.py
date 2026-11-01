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

"""Local patch (2026-10-31): keep a riyaz session alive through device hiccups.

InputWatch: the USB mic sometimes drops off the bus for a second. While it is
gone the sound server moves the capture to another microphone, and when it
comes back it often has a new node name (".2", "stereo-fallback"), which the
saved default doesn't match, so the input stays on the wrong mic. The watch
puts the default source back on the preferred mic whenever it is present, and
reopens the input stream if it stops delivering audio.

HangWatch: if the GUI thread stops turning over, dump every thread's stack to
stderr (the launcher's log), so a freeze leaves evidence behind.
"""

import faulthandler
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from friture.audiobackend import AudioBackend

PREFERRED_INPUT = re.compile(r"Audio_Technica|ATR2500x", re.IGNORECASE)
CHECK_INTERVAL_MS = 2000
INPUT_STALL_S = 3.0        # no audio for this long while recording: reopen the input
REOPEN_BACKOFF_S = 5.0
HANG_S = 3.0               # GUI blocked this long: dump the stacks


def _pactl(*args: str) -> Optional[str]:
    try:
        return subprocess.run(["pactl", *args], capture_output=True, check=True,
                              timeout=3, text=True).stdout
    except Exception:
        return None


def preferred_source() -> Optional[str]:
    """The preferred mic's source name, as it is called right now."""
    out = _pactl("list", "short", "sources")
    if out is None:
        return None
    for line in out.splitlines():
        fields = line.split("\t")
        if len(fields) > 1 and ".monitor" not in fields[1] and PREFERRED_INPUT.search(fields[1]):
            return fields[1]
    return None


class InputWatch(QObject):
    _checked = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._busy = False
        self._last_reopen = 0.0
        self._checked.connect(self._check_stall)
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        # pactl can stall while a device is coming and going: keep it off the GUI thread
        if self._busy or shutil.which("pactl") is None:
            self._check_stall()
            return
        self._busy = True
        threading.Thread(target=self._fix_default_source, daemon=True).start()

    def _fix_default_source(self) -> None:
        try:
            mic = preferred_source()
            default = (_pactl("get-default-source") or "").strip()
            if mic and default != mic:
                self.logger.warning("input was on %s; moving it back to %s", default or "nothing", mic)
                _pactl("set-default-source", mic)
        finally:
            self._busy = False
            self._checked.emit()

    def _check_stall(self) -> None:
        backend = AudioBackend()
        if backend.stream is None or backend.device is None:
            return
        silent = backend.seconds_without_input()
        now = time.monotonic()
        if silent > INPUT_STALL_S and now - self._last_reopen > REOPEN_BACKOFF_S:
            self._last_reopen = now
            self.logger.warning("no audio from the input for %.1f s; reopening it", silent)
            backend.reopen_input()


class HangWatch(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._beat = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        threading.Thread(target=self._watch, daemon=True).start()

    def _tick(self) -> None:
        self._beat = time.monotonic()

    def _watch(self) -> None:
        dumped_for = None
        while True:
            time.sleep(1.0)
            beat = self._beat
            if time.monotonic() - beat > HANG_S and dumped_for != beat:
                dumped_for = beat
                print(f"\n=== GUI thread blocked for {time.monotonic() - beat:.1f} s "
                      f"at {time.strftime('%H:%M:%S')}; stacks: ===", file=sys.stderr, flush=True)
                faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
