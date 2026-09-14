#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2024 Celeste Sinéad

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

from PyQt6 import QtWidgets
from PyQt6.QtCore import QSettings
from typing import Any

from friture.audiobackend import SAMPLING_RATE

# Pitch tracker defaults:
DEFAULT_FFT_SIZE = 4096
DEFAULT_MIN_FREQ = 65
DEFAULT_MAX_FREQ = 1047
DEFAULT_DURATION = 10
DEFAULT_MIN_DB = -50.0
DEFAULT_C_RES = 10      # Pitch resolution in cents. Default of 10 produces 120 kernels per octave.
DEFAULT_P_CONF = 0.50   # Confidence threshold for pitch estimation. Unitless.
DEFAULT_P_DELTA = 2     # Maximum pitch jump between frames in semitones.
DEFAULT_SA_MIDI = 48    # Local patch: tonic (Sa) for the sargam axis. 48 = C3 ≈ 130.8 Hz.
SA_MIDI_RANGE = range(36, 73)  # C2 .. C5

class PitchTrackerSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, view_model: Any) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pitch Tracker Settings")
        self.form_layout = QtWidgets.QFormLayout(self)

        self.min_freq = QtWidgets.QSpinBox(self)
        self.min_freq.setMinimum(10)
        self.min_freq.setMaximum(SAMPLING_RATE // 2)
        self.min_freq.setSingleStep(10)
        self.min_freq.setValue(DEFAULT_MIN_FREQ)
        self.min_freq.setSuffix(" Hz")
        self.min_freq.setObjectName("min_freq")
        self.min_freq.valueChanged.connect(view_model.set_min_freq) # type: ignore
        self.form_layout.addRow("Min:", self.min_freq)

        self.max_freq = QtWidgets.QSpinBox(self)
        self.max_freq.setMinimum(10)
        self.max_freq.setMaximum(SAMPLING_RATE // 2)
        self.max_freq.setSingleStep(10)
        self.max_freq.setValue(DEFAULT_MAX_FREQ)
        self.max_freq.setSuffix(" Hz")
        self.max_freq.setObjectName("max_freq")
        self.max_freq.valueChanged.connect(view_model.set_max_freq) # type: ignore
        self.form_layout.addRow("Max:", self.max_freq)

        self.duration = QtWidgets.QSpinBox(self)
        self.duration.setMinimum(5)
        self.duration.setMaximum(60)
        self.duration.setSingleStep(1)
        self.duration.setValue(DEFAULT_DURATION)
        self.duration.setSuffix(" s")
        self.duration.setObjectName("duration")
        self.duration.valueChanged.connect(view_model.set_duration) # type: ignore
        self.form_layout.addRow("Duration:", self.duration)

        self.conf = QtWidgets.QDoubleSpinBox(self)
        self.conf.setMinimum(0)
        self.conf.setMaximum(1)
        self.conf.setSingleStep(0.01)
        self.conf.setValue(DEFAULT_P_CONF)
        self.conf.setSuffix("")
        self.conf.setObjectName("conf")
        self.conf.valueChanged.connect(view_model.set_conf)
        self.form_layout.addRow("Conf. Cut:", self.conf)

        self.min_db = QtWidgets.QDoubleSpinBox(self)
        self.min_db.setMinimum(-100)
        self.min_db.setMaximum(0)
        self.min_db.setSingleStep(1)
        self.min_db.setValue(DEFAULT_MIN_DB)
        self.min_db.setSuffix(" dB")
        self.min_db.setObjectName("min_db")
        self.min_db.valueChanged.connect(view_model.set_min_db) # type: ignore
        self.form_layout.addRow("Min Amplitude:", self.min_db)

        # Local patch (2026-09-13): tonic for the sargam axis labels/colours.
        from friture.plotting.frequency_scales import midi_to_frequency, midi_to_western
        self.sa = QtWidgets.QComboBox(self)
        for midi in SA_MIDI_RANGE:
            self.sa.addItem(f"{midi_to_western(midi)}  ({midi_to_frequency(midi):.1f} Hz)", midi)
        self.sa.setCurrentIndex(self.sa.findData(DEFAULT_SA_MIDI))
        self.sa.setObjectName("sa")
        self.sa.currentIndexChanged.connect(
            lambda _: view_model.set_sa(self.sa.currentData()))
        self.form_layout.addRow("Sa (tonic):", self.sa)

        # Reference track: a song or a teacher's recording, played back while its
        # pitch curve is drawn alongside the live one.
        self.view_model = view_model
        self.reference_path = ""
        ref_row = QtWidgets.QHBoxLayout()
        self.ref_label = QtWidgets.QLabel("none", self)
        self.ref_label.setMinimumWidth(160)
        self.ref_browse = QtWidgets.QPushButton("Browse…", self)
        self.ref_browse.clicked.connect(self._browse_reference)
        self.ref_clear = QtWidgets.QPushButton("Clear", self)
        self.ref_clear.clicked.connect(self._clear_reference)
        ref_row.addWidget(self.ref_label, 1)
        ref_row.addWidget(self.ref_browse)
        ref_row.addWidget(self.ref_clear)
        self.form_layout.addRow("Reference:", ref_row)

        from friture.reference_track import find_demucs, list_output_devices
        self.isolate = QtWidgets.QCheckBox("Isolate vocals (Demucs)", self)
        self.isolate.setObjectName("isolate_vocals")
        if find_demucs() is None:
            self.isolate.setEnabled(False)
            self.isolate.setToolTip("demucs not found — install it (uv tool install demucs) to separate vocals from a full mix")
        else:
            self.isolate.setToolTip("Separate the vocals from the accompaniment before tracking pitch; a few minutes per song on CPU, cached afterwards")
        self.isolate.toggled.connect(self._on_isolate_toggled)
        self.form_layout.addRow("", self.isolate)

        self.transpose = QtWidgets.QSpinBox(self)
        self.transpose.setRange(-24, 24)
        self.transpose.setValue(0)
        self.transpose.setSuffix(" semitones")
        self.transpose.setObjectName("transpose")
        self.transpose.valueChanged.connect(view_model.set_transpose)
        self.form_layout.addRow("Transpose ref:", self.transpose)

        self.output = QtWidgets.QComboBox(self)
        for label, key in list_output_devices():
            self.output.addItem(label, key)
        self.output.setObjectName("output_device")
        self.output.currentIndexChanged.connect(
            lambda _: view_model.set_output_device(self.output.currentData()))
        self.form_layout.addRow("Play through:", self.output)

        play_row = QtWidgets.QHBoxLayout()
        self.ref_play = QtWidgets.QPushButton("Play", self)
        self.ref_play.setEnabled(False)
        self.ref_play.clicked.connect(self._toggle_reference)
        self.ref_status = QtWidgets.QLabel("", self)
        play_row.addWidget(self.ref_play)
        play_row.addWidget(self.ref_status, 1)
        self.form_layout.addRow("", play_row)

        view_model.reference.loaded.connect(self._on_reference_loaded)
        view_model.reference.progress.connect(self.ref_status.setText)
        view_model.reference.load_failed.connect(self._on_reference_failed)
        view_model.reference.playing_changed.connect(self._on_playing_changed)

        self.setLayout(self.form_layout)

    def _browse_reference(self) -> None:
        start = os.path.dirname(self.reference_path) if self.reference_path else os.path.expanduser("~")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose a reference recording", start,
            "Audio files (*.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.wma *.mp4 *.webm);;All files (*)")
        if path:
            self._set_reference(path)

    def _set_reference(self, path: str) -> None:
        self.reference_path = path
        self.ref_label.setText(os.path.basename(path))
        self.ref_label.setToolTip(path)
        self.ref_status.setText("loading…")
        self.ref_play.setEnabled(False)
        self.view_model.set_reference_file(path, self.isolate.isChecked())

    def _on_isolate_toggled(self, checked: bool) -> None:
        if self.reference_path:
            self._set_reference(self.reference_path)  # re-analyse with/without separation

    def _clear_reference(self) -> None:
        self.reference_path = ""
        self.ref_label.setText("none")
        self.ref_label.setToolTip("")
        self.ref_status.setText("")
        self.ref_play.setEnabled(False)
        self.view_model.clear_reference()

    def _toggle_reference(self) -> None:
        if self.view_model.reference.is_playing():
            self.view_model.stop_reference()
        else:
            self.view_model.play_reference()

    def _on_reference_loaded(self, status: str) -> None:
        self.ref_status.setText(status)
        self.ref_play.setEnabled(True)

    def _on_reference_failed(self, error: str) -> None:
        self.ref_status.setText(f"failed: {error}")
        self.ref_play.setEnabled(False)

    def _on_playing_changed(self, playing: bool) -> None:
        self.ref_play.setText("Stop" if playing else "Play")

    def save_state(self, settings: QSettings) -> None:
        settings.setValue("min_freq", self.min_freq.value())
        settings.setValue("max_freq", self.max_freq.value())
        settings.setValue("duration", self.duration.value())
        settings.setValue("conf", self.conf.value())
        settings.setValue("min_db", self.min_db.value())
        settings.setValue("sa_midi", self.sa.currentData())
        settings.setValue("reference_path", self.reference_path)
        settings.setValue("transpose", self.transpose.value())
        settings.setValue("isolate_vocals", self.isolate.isChecked())
        settings.setValue("output_device", self.output.currentData())

    def restore_state(self, settings: QSettings) -> None:
        self.sa.setCurrentIndex(self.sa.findData(
            settings.value("sa_midi", DEFAULT_SA_MIDI, type=int)))
        self.transpose.setValue(settings.value("transpose", 0, type=int))
        index = self.output.findData(settings.value("output_device", "", type=str))
        self.output.setCurrentIndex(max(index, 0))
        # set the checkbox before the path so the restore triggers one load, not two
        self.isolate.blockSignals(True)
        self.isolate.setChecked(self.isolate.isEnabled() and settings.value("isolate_vocals", False, type=bool))
        self.isolate.blockSignals(False)
        path = settings.value("reference_path", "", type=str)
        if path and os.path.exists(path):
            self._set_reference(path)
        self.min_freq.setValue(
            settings.value("min_freq", DEFAULT_MIN_FREQ, type=int))
        self.max_freq.setValue(
            settings.value("max_freq", DEFAULT_MAX_FREQ, type=int))
        self.duration.setValue(
            settings.value("duration", DEFAULT_DURATION, type=int))
        self.conf.setValue(
            settings.value("conf", DEFAULT_P_CONF, type=float))
        self.min_db.setValue(
            settings.value("min_db", DEFAULT_MIN_DB, type=float))

