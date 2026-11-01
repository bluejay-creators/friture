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

"""Voice monitoring: hear the mic in the headphones while singing.

Delegates to a PulseAudio / PipeWire `module-loopback` rather than copying
samples through Friture's own streams: the sound server's loopback runs at
~20 ms latency, far below what the analysis pipeline's block sizes allow.
Linux only; `available()` is False elsewhere.
"""

import atexit
import json
import logging
import platform
import shutil
import subprocess
from typing import Optional

# Tags our loopback so it can be told apart from any the user loaded by hand,
# found again after a crash, and recognised in pavucontrol.
STREAM_NAME = "friture-voice-monitor"
LATENCY_MS = 20
DEFAULT_VOLUME = 70  # percent


def available() -> bool:
    return platform.system() == "Linux" and shutil.which("pactl") is not None


def _pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True,
                          check=True, timeout=5).stdout


class VoiceMonitor:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.volume = DEFAULT_VOLUME
        self.sink: Optional[str] = None  # None = the system default sink
        self._module: Optional[str] = None
        atexit.register(self.stop)

    def is_running(self) -> bool:
        return self._module is not None

    def start(self) -> None:
        """Loop the default input into `self.sink`. Raises on failure."""
        self.stop()
        self._unload_stale()
        args = ["load-module", "module-loopback", f"latency_msec={LATENCY_MS}",
                f"sink_input_properties=media.name={STREAM_NAME}"]
        if self.sink:
            args.append(f"sink={self.sink}")
        self._module = _pactl(*args).strip()
        self.logger.info("voice monitor on (module %s, sink %s)", self._module, self.sink or "default")
        self.set_volume(self.volume)

    def stop(self) -> None:
        if self._module is None:
            return
        try:
            _pactl("unload-module", self._module)
        except Exception:
            self.logger.exception("could not unload voice monitor module %s", self._module)
        self._module = None

    def set_volume(self, percent: int) -> None:
        self.volume = percent
        stream = self._stream_index()
        if stream is not None:
            _pactl("set-sink-input-volume", stream, f"{percent}%")

    def set_sink(self, sink: Optional[str]) -> None:
        """Follow the song's output so voice and song share the headphones."""
        if sink == self.sink:
            return
        self.sink = sink
        if self.is_running():
            self.start()

    def _stream_index(self) -> Optional[str]:
        if self._module is None:
            return None
        for stream in json.loads(_pactl("-f", "json", "list", "sink-inputs")):
            if str(stream.get("owner_module")) == self._module:
                return str(stream["index"])
        return None

    def _unload_stale(self) -> None:
        """Remove loopbacks left behind by a Friture that crashed or was killed."""
        # the JSON module listing carries no index, so read the short form:
        # "<index>\t<name>\t<arguments>"
        for line in _pactl("list", "short", "modules").splitlines():
            fields = line.split("\t")
            if len(fields) >= 3 and fields[1] == "module-loopback" and STREAM_NAME in fields[2]:
                _pactl("unload-module", fields[0])
