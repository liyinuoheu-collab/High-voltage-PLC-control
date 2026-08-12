"""Collapsible connection, safety and raw-data diagnostics."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class DiagnosticPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        self.toggle_button = QPushButton("▶ 设备与诊断")
        self.toggle_button.setCheckable(True)
        self.toggle_button.toggled.connect(self._set_expanded)
        layout.addWidget(self.toggle_button)
        self.body = QWidget()
        form = QFormLayout(self.body)
        self.protocol_value = QLabel("等待 V6 遥测")
        self.hard_protection_value = QLabel("等待板端状态")
        self.auto_stop_box = QCheckBox("疑似击穿时自动锁定停机")
        self.auto_stop_box.setChecked(True)
        self.drop_threshold = QSpinBox()
        self.drop_threshold.setRange(10, 50)
        self.drop_threshold.setValue(20)
        self.drop_threshold.setSuffix(" %")
        self.raw_text_box = QCheckBox("显示原始串口文本")
        form.addRow("协议", self.protocol_value)
        form.addRow("板端硬保护", self.hard_protection_value)
        form.addRow("", self.auto_stop_box)
        form.addRow("突降判据", self.drop_threshold)
        form.addRow("", self.raw_text_box)
        layout.addWidget(self.body)
        self._set_expanded(False)

    @property
    def expanded(self) -> bool:
        return self.body.isVisible()

    def _set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setText(("▼" if expanded else "▶") + " 设备与诊断")

