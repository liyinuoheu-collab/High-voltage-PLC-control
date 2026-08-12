"""Collapsible, typed experiment-parameter controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExperimentControlPanel(QFrame):
    voltage_requested = Signal(int)
    waveform_requested = Signal(str)
    period_requested = Signal(int)
    duty_requested = Signal(int)
    phase_requested = Signal(int)
    duration_requested = Signal(int)
    clear_requested = Signal(bool)

    voltage_values = [4000, 4500, 5000, 5500, 6000, 6500, 7000]
    period_values = [5000, 2500, 1250, 625]
    duty_values = [25, 50, 75]
    phase_values = [0, 90, 180]
    duration_values = [10000, 20000, 30000, 60000, 0]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        self.toggle_button = QPushButton("▶ 实验参数")
        self.toggle_button.setCheckable(True)
        self.toggle_button.toggled.connect(self._set_expanded)
        layout.addWidget(self.toggle_button)
        self.body = QWidget()
        form = QFormLayout(self.body)

        self.voltage_box = self._number_box(self.voltage_values, " V")
        self.voltage_box.setCurrentText("7000 V")
        self.waveform_box = QComboBox()
        self.waveform_box.addItems(["HOLD", "SQUARE"])
        self.waveform_box.setCurrentText("SQUARE")
        self.period_box = QComboBox()
        for value, label in (
            (5000, "0.2 Hz"),
            (2500, "0.4 Hz"),
            (1250, "0.8 Hz"),
            (625, "1.6 Hz"),
        ):
            self.period_box.addItem(label, value)
        self.period_box.setCurrentIndex(1)
        self.duty_box = self._number_box(self.duty_values, " %")
        self.duty_box.setCurrentText("50 %")
        self.phase_box = self._number_box(self.phase_values, "°")
        self.duration_box = QComboBox()
        for value, label in (
            (10000, "10 s"),
            (20000, "20 s"),
            (30000, "30 s"),
            (60000, "60 s"),
            (0, "一直驱动"),
        ):
            self.duration_box.addItem(label, value)
        self.duration_box.setCurrentIndex(1)
        self.clear_box = QCheckBox("结束后 3 kV / 200 ms 清荷")
        self.clear_box.setChecked(True)

        form.addRow("设定电压", self.voltage_box)
        form.addRow("波形", self.waveform_box)
        form.addRow("方波频率", self.period_box)
        form.addRow("占空比", self.duty_box)
        form.addRow("左右相位差", self.phase_box)
        form.addRow("总驱动时长", self.duration_box)
        form.addRow("", self.clear_box)
        apply_row = QHBoxLayout()
        self.apply_button = QPushButton("应用待机参数")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self._emit_requests)
        apply_row.addStretch()
        apply_row.addWidget(self.apply_button)
        form.addRow(apply_row)
        layout.addWidget(self.body)
        self._set_expanded(False)

    @staticmethod
    def _number_box(values: list[int], suffix: str) -> QComboBox:
        box = QComboBox()
        for value in values:
            box.addItem(f"{value}{suffix}", value)
        return box

    @property
    def expanded(self) -> bool:
        return self.body.isVisible()

    def _set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setText(("▼" if expanded else "▶") + " 实验参数")

    def _emit_requests(self) -> None:
        self.voltage_requested.emit(int(self.voltage_box.currentData()))
        self.waveform_requested.emit(self.waveform_box.currentText())
        if self.waveform_box.currentText() == "SQUARE":
            self.period_requested.emit(int(self.period_box.currentData()))
            self.duty_requested.emit(int(self.duty_box.currentData()))
            self.phase_requested.emit(int(self.phase_box.currentData()))
        self.duration_requested.emit(int(self.duration_box.currentData()))
        self.clear_requested.emit(self.clear_box.isChecked())

    def set_editable(self, editable: bool) -> None:
        for widget in (
            self.voltage_box,
            self.waveform_box,
            self.period_box,
            self.duty_box,
            self.phase_box,
            self.duration_box,
            self.clear_box,
            self.apply_button,
        ):
            widget.setEnabled(editable)

