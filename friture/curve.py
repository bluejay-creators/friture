#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2021 Timothée Lecomte

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

from PyQt6 import QtCore
from PyQt6.QtCore import pyqtProperty # type: ignore
import numpy

class Curve(QtCore.QObject):
    data_changed = QtCore.pyqtSignal()
    name_changed = QtCore.pyqtSignal(str)
    color_changed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._name = ""
        # Local patch (2026-09-25): per-curve colour; empty falls back to the
        # shared plotItemColors palette.
        self._color = ""
        self._x_array = numpy.array([0])
        self._y_array = numpy.array([0])
        # Local patch (2026-09-25): optional per-sample RGBA (N x 4 uint8), used
        # by the pitch tracker to shade the curve by intonation. None = draw the
        # whole curve in `color`.
        self._color_array = None

    def setData(self, x_array, y_array, color_array=None):
        self._x_array = x_array
        self._y_array = y_array
        self._color_array = color_array
        self.data_changed.emit()

    def x_array(self):
        return self._x_array

    def y_array(self):
        return self._y_array

    def color_array(self):
        return self._color_array

    @pyqtProperty(str, notify=color_changed)
    def color(self):
        return self._color

    @color.setter # type: ignore
    def color(self, color):
        if self._color != color:
            self._color = color
            self.color_changed.emit(color)

    @pyqtProperty(str, notify=name_changed)
    def name(self):
        return self._name

    @name.setter # type: ignore
    def name(self, name):
        if self._name != name:
            self._name = name
            self.name_changed.emit(name)