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

import logging
import os

from PyQt6 import QtWidgets
from PyQt6.QtCore import QSettings, Qt
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

        from friture.plotting.frequency_scales import GRID_STYLES, DEFAULT_GRID_STYLE
        self.grid_style = QtWidgets.QComboBox(self)
        for label, key in GRID_STYLES:
            self.grid_style.addItem(label, key)
        self.grid_style.setCurrentIndex(self.grid_style.findData(DEFAULT_GRID_STYLE))
        self.grid_style.setObjectName("grid_style")
        self.grid_style.setToolTip("How the swara grid lines and scale labels are coloured")
        self.grid_style.currentIndexChanged.connect(
            lambda _: view_model.set_grid_style(self.grid_style.currentData()))
        self.form_layout.addRow("Grid colours:", self.grid_style)

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

        # Voice monitoring: the mic in the headphones, on the same output as the
        # song, so the singer hears both together.
        from friture.voice_monitor import DEFAULT_VOLUME, available as monitor_available
        monitor_row = QtWidgets.QHBoxLayout()
        self.monitor_on = QtWidgets.QCheckBox("On", self)
        self.monitor_on.setObjectName("monitor_on")
        self.monitor_volume = QtWidgets.QSlider(Qt.Orientation.Horizontal, self)
        self.monitor_volume.setRange(0, 150)
        self.monitor_volume.setValue(DEFAULT_VOLUME)
        self.monitor_volume.setObjectName("monitor_volume")
        self.monitor_volume_label = QtWidgets.QLabel(f"{DEFAULT_VOLUME}%", self)
        self.monitor_volume_label.setMinimumWidth(40)
        monitor_row.addWidget(self.monitor_on)
        monitor_row.addWidget(self.monitor_volume, 1)
        monitor_row.addWidget(self.monitor_volume_label)
        if monitor_available():
            self.monitor_on.setToolTip("Hear your mic in the \"Play through\" output (~20 ms delay)")
        else:
            for w in (self.monitor_on, self.monitor_volume):
                w.setEnabled(False)
            self.monitor_on.setToolTip("Needs PulseAudio / PipeWire (pactl) on Linux")
        self.monitor_on.toggled.connect(self._on_monitor_toggled)
        self.monitor_volume.valueChanged.connect(self._on_monitor_volume)
        self.form_layout.addRow("Hear my voice:", monitor_row)

        # Taal metronome, on the same output as the song; its beats are drawn
        # on the timeline (sam red, khali blue, tali grey).
        from friture.metronome import TAALS, DEFAULT_TAAL, DEFAULT_BPM, BPM_RANGE, DEFAULT_VOLUME as METRONOME_VOLUME
        metronome_row = QtWidgets.QHBoxLayout()
        self.metronome_on = QtWidgets.QCheckBox("On", self)
        self.metronome_on.setObjectName("metronome_on")
        self.taal = QtWidgets.QComboBox(self)
        for label, key, _ in TAALS:
            self.taal.addItem(label, key)
        self.taal.setCurrentIndex(self.taal.findData(DEFAULT_TAAL))
        self.taal.setObjectName("taal")
        self.bpm = QtWidgets.QSpinBox(self)
        self.bpm.setRange(*BPM_RANGE)
        self.bpm.setValue(DEFAULT_BPM)
        self.bpm.setSuffix(" bpm")
        self.bpm.setObjectName("bpm")
        metronome_row.addWidget(self.metronome_on)
        metronome_row.addWidget(self.taal, 1)
        metronome_row.addWidget(self.bpm)
        self.form_layout.addRow("Metronome:", metronome_row)

        metronome_volume_row = QtWidgets.QHBoxLayout()
        self.metronome_volume = QtWidgets.QSlider(Qt.Orientation.Horizontal, self)
        self.metronome_volume.setRange(0, 100)
        self.metronome_volume.setValue(METRONOME_VOLUME)
        self.metronome_volume.setObjectName("metronome_volume")
        self.metronome_volume_label = QtWidgets.QLabel(f"{METRONOME_VOLUME}%", self)
        self.metronome_volume_label.setMinimumWidth(40)
        self.metronome_sound = QtWidgets.QCheckBox("Sound", self)
        self.metronome_sound.setChecked(True)
        self.metronome_sound.setObjectName("metronome_sound")
        self.metronome_sound.setToolTip("Untick for a silent metronome: the beats are still drawn")
        metronome_volume_row.addWidget(self.metronome_sound)
        metronome_volume_row.addWidget(self.metronome_volume, 1)
        metronome_volume_row.addWidget(self.metronome_volume_label)
        self.form_layout.addRow("Click volume:", metronome_volume_row)

        self.metronome_on.toggled.connect(self._on_metronome_toggled)
        self.taal.currentIndexChanged.connect(
            lambda _: view_model.set_metronome_taal(self.taal.currentData()))
        self.bpm.valueChanged.connect(view_model.set_metronome_bpm)
        self.metronome_volume.valueChanged.connect(self._on_metronome_volume)
        self.metronome_sound.toggled.connect(view_model.set_metronome_sound)
        self.metronome_sound.toggled.connect(self.metronome_volume.setEnabled)

        # Tanpura drone on an output of its own, so it can fill the room from a
        # speaker while everything above stays in the headphones.
        from friture.tanpura import TUNINGS, DEFAULT_TUNING, DEFAULT_VOLUME as TANPURA_VOLUME, FINE_TUNE_RANGE
        tanpura_row = QtWidgets.QHBoxLayout()
        self.tanpura_on = QtWidgets.QCheckBox("On", self)
        self.tanpura_on.setObjectName("tanpura_on")
        self.tanpura_tuning = QtWidgets.QComboBox(self)
        for label, key, *_ in TUNINGS:
            self.tanpura_tuning.addItem(label, key)
        self.tanpura_tuning.setCurrentIndex(self.tanpura_tuning.findData(DEFAULT_TUNING))
        self.tanpura_tuning.setObjectName("tanpura_tuning")
        self.tanpura_tuning.setToolTip("First string: Pa, Ma, Ni or Dha, then Sa Sa and low Sa")
        self.tanpura_cents = QtWidgets.QSpinBox(self)
        self.tanpura_cents.setRange(*FINE_TUNE_RANGE)
        self.tanpura_cents.setSuffix(" ¢")
        self.tanpura_cents.setObjectName("tanpura_cents")
        self.tanpura_cents.setToolTip("Fine-tune the tanpura against the Sa above, in cents")
        tanpura_row.addWidget(self.tanpura_on)
        tanpura_row.addWidget(self.tanpura_tuning, 1)
        tanpura_row.addWidget(self.tanpura_cents)
        self.form_layout.addRow("Tanpura:", tanpura_row)

        self.tanpura_output = QtWidgets.QComboBox(self)
        for label, key in list_output_devices():
            self.tanpura_output.addItem(label, key)
        self.tanpura_output.setObjectName("tanpura_output_device")
        self.form_layout.addRow("Tanpura through:", self.tanpura_output)

        tanpura_volume_row = QtWidgets.QHBoxLayout()
        self.tanpura_volume = QtWidgets.QSlider(Qt.Orientation.Horizontal, self)
        self.tanpura_volume.setRange(0, 100)
        self.tanpura_volume.setValue(TANPURA_VOLUME)
        self.tanpura_volume.setObjectName("tanpura_volume")
        self.tanpura_volume_label = QtWidgets.QLabel(f"{TANPURA_VOLUME}%", self)
        self.tanpura_volume_label.setMinimumWidth(40)
        tanpura_volume_row.addWidget(self.tanpura_volume, 1)
        tanpura_volume_row.addWidget(self.tanpura_volume_label)
        self.form_layout.addRow("Tanpura volume:", tanpura_volume_row)
        tanpura_status_row = QtWidgets.QHBoxLayout()
        self.tanpura_lines = QtWidgets.QCheckBox("Show notes on plot", self)
        self.tanpura_lines.setChecked(True)
        self.tanpura_lines.setObjectName("tanpura_lines")
        self.tanpura_lines.setToolTip("Draw the drone's notes as purple lines while it plays")
        self.tanpura_status = QtWidgets.QLabel("", self)
        tanpura_status_row.addWidget(self.tanpura_lines)
        tanpura_status_row.addWidget(self.tanpura_status, 1)
        self.form_layout.addRow("", tanpura_status_row)

        self.tanpura_on.toggled.connect(view_model.set_tanpura_enabled)
        self.tanpura_tuning.currentIndexChanged.connect(
            lambda _: view_model.set_tanpura_tuning(self.tanpura_tuning.currentData()))
        self.tanpura_cents.valueChanged.connect(view_model.set_tanpura_cents)
        self.tanpura_output.currentIndexChanged.connect(
            lambda _: view_model.set_tanpura_output_device(self.tanpura_output.currentData()))
        self.tanpura_volume.valueChanged.connect(self._on_tanpura_volume)
        self.tanpura_lines.toggled.connect(view_model.set_tanpura_lines)
        view_model.tanpura.state_changed.connect(self.tanpura_status.setText)

        view_model.reference.loaded.connect(self._on_reference_loaded)
        view_model.reference.progress.connect(self.ref_status.setText)
        view_model.reference.load_failed.connect(self._on_reference_failed)
        view_model.reference.playing_changed.connect(self._on_playing_changed)

        self.setLayout(self.form_layout)

    def _on_monitor_toggled(self, checked: bool) -> None:
        try:
            self.view_model.set_monitor_enabled(checked)
        except Exception as e:
            self.monitor_on.blockSignals(True)
            self.monitor_on.setChecked(False)
            self.monitor_on.blockSignals(False)
            self.monitor_on.setToolTip(f"could not start monitoring: {e}")

    def _on_metronome_toggled(self, checked: bool) -> None:
        self.view_model.set_metronome_enabled(checked)
        if checked and not self.view_model.metronome.is_running():
            self.metronome_on.blockSignals(True)
            self.metronome_on.setChecked(False)
            self.metronome_on.blockSignals(False)
            self.metronome_on.setToolTip("could not open the output device; see the log")

    def _on_metronome_volume(self, percent: int) -> None:
        self.metronome_volume_label.setText(f"{percent}%")
        self.view_model.set_metronome_volume(percent)

    def _on_tanpura_volume(self, percent: int) -> None:
        self.tanpura_volume_label.setText(f"{percent}%")
        self.view_model.set_tanpura_volume(percent)

    def _select_saved_device(self, combo: QtWidgets.QComboBox, key: str, label: str) -> None:
        """Select a saved output, keeping it even when it isn't connected right
        now (a Bluetooth speaker that's off) instead of falling back to the
        default output, which would put the sound in the headphones."""
        index = combo.findData(key)
        if index < 0 and key:
            combo.addItem(f"{label or key} (not connected)", key)
            index = combo.count() - 1
        combo.setCurrentIndex(max(index, 0))

    def _on_monitor_volume(self, percent: int) -> None:
        self.monitor_volume_label.setText(f"{percent}%")
        try:
            self.view_model.set_monitor_volume(percent)
        except Exception:
            logging.getLogger(__name__).exception("could not set monitor volume")

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
        settings.setValue("grid_style", self.grid_style.currentData())
        settings.setValue("reference_path", self.reference_path)
        settings.setValue("transpose", self.transpose.value())
        settings.setValue("isolate_vocals", self.isolate.isChecked())
        settings.setValue("output_device", self.output.currentData())
        settings.setValue("monitor_on", self.monitor_on.isChecked())
        settings.setValue("monitor_volume", self.monitor_volume.value())
        settings.setValue("taal", self.taal.currentData())
        settings.setValue("bpm", self.bpm.value())
        settings.setValue("metronome_volume", self.metronome_volume.value())
        settings.setValue("metronome_sound", self.metronome_sound.isChecked())
        settings.setValue("tanpura_lines", self.tanpura_lines.isChecked())
        settings.setValue("tanpura_tuning", self.tanpura_tuning.currentData())
        settings.setValue("tanpura_cents", self.tanpura_cents.value())
        settings.setValue("tanpura_output_device", self.tanpura_output.currentData())
        settings.setValue("tanpura_output_label",
                          self.tanpura_output.currentText().removesuffix(" (not connected)"))
        settings.setValue("tanpura_volume", self.tanpura_volume.value())

    def restore_state(self, settings: QSettings) -> None:
        self.sa.setCurrentIndex(self.sa.findData(
            settings.value("sa_midi", DEFAULT_SA_MIDI, type=int)))
        from friture.plotting.frequency_scales import DEFAULT_GRID_STYLE
        index = self.grid_style.findData(settings.value("grid_style", DEFAULT_GRID_STYLE, type=str))
        self.grid_style.setCurrentIndex(max(index, 0))
        self.transpose.setValue(settings.value("transpose", 0, type=int))
        index = self.output.findData(settings.value("output_device", "", type=str))
        self.output.setCurrentIndex(max(index, 0))
        # after the output, so monitoring starts on the right sink
        from friture.voice_monitor import DEFAULT_VOLUME
        self.monitor_volume.setValue(settings.value("monitor_volume", DEFAULT_VOLUME, type=int))
        self.monitor_on.setChecked(self.monitor_on.isEnabled() and settings.value("monitor_on", False, type=bool))
        # the metronome always starts off: a click on launch would be a surprise
        from friture.metronome import DEFAULT_TAAL, DEFAULT_BPM, DEFAULT_VOLUME as METRONOME_VOLUME
        index = self.taal.findData(settings.value("taal", DEFAULT_TAAL, type=str))
        self.taal.setCurrentIndex(max(index, 0))
        self.bpm.setValue(settings.value("bpm", DEFAULT_BPM, type=int))
        self.metronome_volume.setValue(settings.value("metronome_volume", METRONOME_VOLUME, type=int))
        self.metronome_sound.setChecked(settings.value("metronome_sound", True, type=bool))
        self.tanpura_lines.setChecked(settings.value("tanpura_lines", True, type=bool))
        # the tanpura also starts off; its settings are restored for the next switch-on
        from friture.tanpura import DEFAULT_TUNING, DEFAULT_VOLUME as TANPURA_VOLUME
        index = self.tanpura_tuning.findData(settings.value("tanpura_tuning", DEFAULT_TUNING, type=str))
        self.tanpura_tuning.setCurrentIndex(max(index, 0))
        self.tanpura_cents.setValue(settings.value("tanpura_cents", 0, type=int))
        self._select_saved_device(self.tanpura_output,
                                  settings.value("tanpura_output_device", "", type=str),
                                  settings.value("tanpura_output_label", "", type=str))
        self.tanpura_volume.setValue(settings.value("tanpura_volume", TANPURA_VOLUME, type=int))
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

