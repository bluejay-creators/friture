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

import time
import unittest
from unittest import mock

from friture import riyaz_watch
from friture.audiobackend import AudioBackend


class PreferredSourceTest(unittest.TestCase):
    def test_finds_the_mic_under_whatever_name_it_came_back_with(self):
        listing = ("1\talsa_input.usb-046d_Logitech_Webcam_C925e-02.analog-stereo\tPipeWire\n"
                   "2\talsa_input.usb-Audio_Technica_Corp_ATR2500x-USB_Microphone-00.analog-stereo.monitor\tPipeWire\n"
                   "3\talsa_input.usb-Audio_Technica_Corp_ATR2500x-USB_Microphone-00.analog-stereo.3\tPipeWire\n")
        with mock.patch.object(riyaz_watch, "_pactl", return_value=listing):
            self.assertEqual(riyaz_watch.preferred_source(),
                             "alsa_input.usb-Audio_Technica_Corp_ATR2500x-USB_Microphone-00.analog-stereo.3")

    def test_none_when_the_mic_is_unplugged(self):
        with mock.patch.object(riyaz_watch, "_pactl", return_value="1\talsa_input.pci.analog-stereo\tPipeWire\n"):
            self.assertIsNone(riyaz_watch.preferred_source())


class InputLivenessTest(unittest.TestCase):
    def test_counts_silence_only_while_the_input_is_being_read(self):
        backend = AudioBackend()
        now = time.monotonic()
        backend._last_fetch, backend._last_input = now, now - 5
        self.assertGreater(backend.seconds_without_input(), 4.9)
        backend._last_fetch = now - 10                 # paused: not being read
        self.assertEqual(backend.seconds_without_input(), 0.0)


if __name__ == '__main__':
    unittest.main()
