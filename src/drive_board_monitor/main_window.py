"""PySide6 monitor/controller for the Donut-HASEL firmware V6 protocol."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .buffer import RollingPlotBuffer
from .commands import BoardCommand
from .control_panel import ExperimentControlPanel
from .diagnostic_panel import DiagnosticPanel
from .models import ParsedSerialLine, ReceivedSerialLine
from .serial_worker import QtSerialWorker, list_serial_ports
from .safety_controller import SafetyController
from .session import SessionController


APP_STYLE = """
QMainWindow, QWidget { background: #0b1020; color: #e6edf7; font-family: "Microsoft YaHei UI"; }
QFrame#card { background: #141c2e; border: 1px solid #263552; border-radius: 10px; }
QLabel#title { font-size: 24px; font-weight: 700; color: #f7f9fc; }
QLabel#subtitle { color: #8da2c4; }
QLabel#cardTitle { color: #91a4c5; font-size: 12px; }
QLabel#cardValue { color: #f2f6ff; font-size: 19px; font-weight: 650; }
QPushButton { background: #243452; border: 1px solid #39527d; border-radius: 6px; padding: 7px 13px; }
QPushButton:hover { background: #2d4269; }
QPushButton:disabled { color: #63708a; background: #172033; border-color: #24304a; }
QPushButton#primary { background: #176b87; border-color: #2594b7; }
QPushButton#record { background: #8b3341; border-color: #bd5263; }
QComboBox, QLineEdit { background: #10182a; border: 1px solid #304260; border-radius: 5px; padding: 6px; }
QTextEdit { background: #0d1423; border: 1px solid #263552; border-radius: 6px; font-family: Consolas; }
QCheckBox { spacing: 6px; }
"""


def format_run_duration(duration_ms: int, inferred: bool = False) -> str:
    """Format the board-selected total run duration for the status card."""
    if duration_ms == 0:
        return "持续运行 · 按 CH 结束"
    seconds = duration_ms / 1000
    text = f"{seconds:g} s"
    return f"{text}（V3 默认）" if inferred else text


def _card(title: str, initial: str = "—") -> tuple[QFrame, QLabel]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 10, 14, 10)
    label = QLabel(title)
    label.setObjectName("cardTitle")
    value = QLabel(initial)
    value.setObjectName("cardValue")
    value.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(label)
    layout.addWidget(value)
    return frame, value


class MainWindow(QMainWindow):
    def __init__(self, auto_refresh_ports: bool = True) -> None:
        super().__init__()
        font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            self.setFont(QFont(families[0], 9))
        self.setWindowTitle("Donut-HASEL 相位差高压驱动监控 V3")
        self.resize(1320, 820)
        self.setStyleSheet(APP_STYLE)
        self.controller = SessionController(window_seconds=30.0)
        self.safety = SafetyController()
        self._serial_thread: QThread | None = None
        self._serial_worker = None
        self._connected = False
        self._event_cursor = 0
        self._analysis_cursor = 0
        self._build_ui()
        self._plot_timer = QTimer(self)
        self._plot_timer.setInterval(50)
        self._plot_timer.timeout.connect(self._refresh_plot)
        self._plot_timer.start()
        if auto_refresh_ports:
            self.refresh_ports()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(12)

        title_row = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Donut-HASEL 驱动板实时监控")
        title.setObjectName("title")
        subtitle = QLabel("50 Hz 板端遥测 · 电脑双时间戳 · 原始数据持续落盘")
        subtitle.setObjectName("subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        title_row.addLayout(titles)
        title_row.addStretch()
        self.link_mode_label = QLabel("● PB6/PB7 双向控制 · V6")
        self.link_mode_label.setStyleSheet("color:#68d391;font-weight:600;")
        title_row.addWidget(self.link_mode_label)
        outer.addLayout(title_row)
        self.safety_banner = QLabel(
            "疑似击穿自动停机：已开启（仅上位机连接时有效；板端硬保护始终独立启用）"
        )
        self.safety_banner.setStyleSheet(
            "background:#183d36;color:#8ff0cf;padding:7px;border-radius:5px;"
        )
        outer.addWidget(self.safety_banner)

        connection = QFrame()
        connection.setObjectName("card")
        row = QHBoxLayout(connection)
        row.addWidget(QLabel("串口"))
        self.port_box = QComboBox()
        self.port_box.setMinimumWidth(220)
        row.addWidget(self.port_box)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_ports)
        row.addWidget(self.refresh_button)
        row.addWidget(QLabel("115200 · 8N1"))
        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(self.toggle_connection)
        row.addWidget(self.connect_button)
        self.connection_value = QLabel("未连接")
        self.connection_value.setStyleSheet("color:#f6ad55;font-weight:600;")
        row.addWidget(self.connection_value)
        row.addStretch()
        self.start_button = QPushButton("启动驱动")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(
            lambda: self._send_command(BoardCommand.start())
        )
        row.addWidget(self.start_button)
        self.stop_button = QPushButton("正常停机")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(
            lambda: self._send_command(BoardCommand.stop())
        )
        row.addWidget(self.stop_button)
        self.unlock_button = QPushButton("故障解锁")
        self.unlock_button.setEnabled(False)
        self.unlock_button.clicked.connect(self._confirm_unlock)
        row.addWidget(self.unlock_button)
        outer.addWidget(connection)

        cards = QGridLayout()
        card_specs = [
            ("模式", "mode_value"),
            ("实验状态", "state_value"),
            ("设定总驱动时长", "duration_value"),
            ("运行编号", "run_value"),
            ("末端清荷", "clear_value"),
            ("输出命令", "command_value"),
            ("反馈幅值", "feedback_value"),
            ("左右相位差", "phase_value"),
            ("输出路由", "route_value"),
            ("故障筛选", "fault_value"),
        ]
        for index, (label, attr) in enumerate(card_specs):
            frame, value = _card(label)
            setattr(self, attr, value)
            cards.addWidget(frame, index // 5, index % 5)
        outer.addLayout(cards)

        panel_row = QHBoxLayout()
        self.control_panel = ExperimentControlPanel()
        self.diagnostic_panel = DiagnosticPanel()
        self.control_panel.voltage_requested.connect(
            lambda value: self._send_command(BoardCommand.set_voltage(value))
        )
        self.control_panel.waveform_requested.connect(
            lambda value: self._send_command(BoardCommand.set_waveform(value))
        )
        self.control_panel.period_requested.connect(
            lambda value: self._send_command(BoardCommand.set_period_ms(value))
        )
        self.control_panel.duty_requested.connect(
            lambda value: self._send_command(BoardCommand.set_duty(value))
        )
        self.control_panel.phase_requested.connect(
            lambda value: self._send_command(BoardCommand.set_phase(value))
        )
        self.control_panel.duration_requested.connect(
            lambda value: self._send_command(BoardCommand.set_duration(value))
        )
        self.control_panel.clear_requested.connect(
            lambda value: self._send_command(BoardCommand.set_clear(value))
        )
        self.diagnostic_panel.auto_stop_box.toggled.connect(
            self._on_auto_stop_toggled
        )
        panel_row.addWidget(self.control_panel, 1)
        panel_row.addWidget(self.diagnostic_panel, 1)
        outer.addLayout(panel_row)

        splitter = QSplitter(Qt.Horizontal)
        plot_panel = QFrame()
        plot_panel.setObjectName("card")
        plot_layout = QVBoxLayout(plot_panel)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("滚动窗口"))
        self.window_seconds_box = QComboBox()
        self.window_seconds_box.addItems(["10 s", "30 s", "60 s", "120 s"])
        self.window_seconds_box.setCurrentText("30 s")
        self.window_seconds_box.currentTextChanged.connect(self._change_window)
        controls.addWidget(self.window_seconds_box)
        self.smoothing_box = QCheckBox("仅显示平滑（原始 CSV 不变）")
        controls.addWidget(self.smoothing_box)
        controls.addStretch()
        self.sample_count_label = QLabel("遥测 0 · 丢帧 0 · 解析错误 0")
        controls.addWidget(self.sample_count_label)
        plot_layout.addLayout(controls)
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#0d1423")
        self.plot.showGrid(x=True, y=True, alpha=0.22)
        self.plot.setLabel("left", "电压", units="V")
        self.plot.setLabel("bottom", "")
        self.plot.addLegend(offset=(12, 10))
        self.command_curve = self.plot.plot(
            pen=pg.mkPen("#4da3ff", width=2), name="Vcmd（板端命令）"
        )
        self.feedback_curve = self.plot.plot(
            pen=pg.mkPen("#ffb454", width=2), name="Vreal（板载反馈）"
        )
        plot_layout.addWidget(self.plot)
        self.route_plot = pg.PlotWidget()
        self.route_plot.setBackground("#0d1423")
        self.route_plot.setMaximumHeight(150)
        self.route_plot.showGrid(x=True, y=True, alpha=0.18)
        self.route_plot.setLabel("left", "路由")
        self.route_plot.setLabel("bottom", "电脑单调时间", units="s")
        self.route_plot.setYRange(-0.2, 2.3)
        self.route_plot.setXLink(self.plot)
        self.left_curve = self.route_plot.plot(
            pen=pg.mkPen("#68d391", width=2), name="LEFT"
        )
        self.right_curve = self.route_plot.plot(
            pen=pg.mkPen("#b794f4", width=2), name="RIGHT"
        )
        plot_layout.addWidget(self.route_plot)
        splitter.addWidget(plot_panel)

        event_panel = QFrame()
        event_panel.setObjectName("card")
        event_layout = QVBoxLayout(event_panel)
        event_layout.addWidget(QLabel("事件时间线"))
        self.event_view = QTextEdit()
        self.event_view.setReadOnly(True)
        self.event_view.document().setMaximumBlockCount(1000)
        event_layout.addWidget(self.event_view)
        splitter.addWidget(event_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        record_panel = QFrame()
        record_panel.setObjectName("card")
        record_row = QHBoxLayout(record_panel)
        record_row.addWidget(QLabel("记录根目录"))
        self.output_dir_edit = QLineEdit(
            str(Path.home() / "Documents" / "Donut-HASEL-data")
        )
        record_row.addWidget(self.output_dir_edit, 1)
        browse = QPushButton("选择…")
        browse.clicked.connect(self.choose_output_dir)
        record_row.addWidget(browse)
        self.start_record_button = QPushButton("开始记录")
        self.start_record_button.setObjectName("record")
        self.start_record_button.setEnabled(False)
        self.start_record_button.clicked.connect(self.start_recording)
        record_row.addWidget(self.start_record_button)
        self.stop_record_button = QPushButton("停止并封存")
        self.stop_record_button.setEnabled(False)
        self.stop_record_button.clicked.connect(self.stop_recording)
        record_row.addWidget(self.stop_record_button)
        self.record_status = QLabel("未记录（时长无软件上限）")
        record_row.addWidget(self.record_status)
        outer.addWidget(record_panel)

        self.setCentralWidget(root)

    def refresh_ports(self) -> None:
        current = self.port_box.currentData()
        self.port_box.clear()
        try:
            ports = list_serial_ports()
        except Exception as exc:
            self.connection_value.setText(f"枚举失败：{exc}")
            return
        for device, description in ports:
            self.port_box.addItem(f"{device} — {description}", device)
        if current:
            index = self.port_box.findData(current)
            if index >= 0:
                self.port_box.setCurrentIndex(index)

    def toggle_connection(self) -> None:
        if self._serial_thread is not None:
            self.disconnect_board()
            return
        port = self.port_box.currentData()
        if not port:
            QMessageBox.warning(self, "没有串口", "请先连接 USB-TTL 并点击刷新。")
            return
        self.connection_value.setText("连接中…")
        self.connect_button.setEnabled(False)
        thread = QThread(self)
        worker = QtSerialWorker(port, 115200)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.connected.connect(self._on_connected)
        worker.line_received.connect(self.handle_received_line)
        worker.disconnected.connect(self._on_disconnected)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)
        self._serial_thread = thread
        self._serial_worker = worker
        thread.start()

    def _on_connected(self) -> None:
        self._connected = True
        self.safety.reset_for_connection()
        self.diagnostic_panel.auto_stop_box.blockSignals(True)
        self.diagnostic_panel.auto_stop_box.setChecked(True)
        self.diagnostic_panel.auto_stop_box.blockSignals(False)
        self._update_safety_banner()
        self.connection_value.setText("已连接 · 等待数据")
        self.connection_value.setStyleSheet("color:#68d391;font-weight:600;")
        self.connect_button.setText("断开")
        self.connect_button.setEnabled(True)
        self.port_box.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.start_record_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self._append_event("PC", "串口已连接；前端与红外遥控均可控制")

    def _on_disconnected(self, detail: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="microseconds")
        session_dir = self.controller.connection_lost(detail, now, time.monotonic_ns())
        self._append_event("SERIAL_DISCONNECTED", detail)
        if session_dir:
            self.record_status.setText(f"断线封存：{session_dir}")
        self._connected = False

    def _on_thread_finished(self) -> None:
        self._serial_thread = None
        self._serial_worker = None
        self.connection_value.setText("未连接")
        self.connection_value.setStyleSheet("color:#f6ad55;font-weight:600;")
        self.connect_button.setText("连接")
        self.connect_button.setEnabled(True)
        self.port_box.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.start_record_button.setEnabled(False)
        self.stop_record_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.unlock_button.setEnabled(False)
        self.control_panel.set_editable(False)

    def disconnect_board(self) -> None:
        if self._serial_worker is not None and hasattr(
            self._serial_worker, "request_stop"
        ):
            self._serial_worker.request_stop()
        if self._serial_thread is not None:
            self._serial_thread.quit()
            self._serial_thread.wait(1000)
        if self.controller.is_recording:
            session_dir = self.controller.stop_recording("manual_disconnect")
            self.record_status.setText(f"已封存：{session_dir}")
        self._on_thread_finished()

    def handle_received_line(self, received: ReceivedSerialLine) -> None:
        before = len(self.controller.events)
        analysis_before = len(self.controller.analysis_events)
        parsed = self.controller.process(received)
        if parsed.kind == "telemetry" and parsed.telemetry is not None:
            item = parsed.telemetry
            self.mode_value.setText(item.mode_name)
            self.state_value.setText(item.state_name)
            self.duration_value.setText(
                format_run_duration(item.run_duration_ms, item.run_duration_inferred)
            )
            self.run_value.setText(str(item.run_id))
            self.clear_value.setText("开启" if item.end_clear else "关闭")
            self.command_value.setText(f"{item.command_voltage_v / 1000:.3f} kV · {item.output_kind}")
            self.feedback_value.setText(f"{item.feedback_hv_magnitude_v / 1000:.3f} kV（幅值）")
            self.phase_value.setText(f"{item.phase_deg}°")
            self.route_value.setText(
                f"L={item.left_state} · R={item.right_state} · {item.output_kind}"
            )
            if item.locked:
                self.fault_value.setText(f"板端锁定 · 故障码 {item.fault_code}")
            elif item.fault_code:
                self.fault_value.setText(f"故障码 {item.fault_code}")
            else:
                self.fault_value.setText("正常")
            self.diagnostic_panel.protocol_value.setText(
                f"V{item.protocol_version} · 50 Hz"
            )
            self.diagnostic_panel.hard_protection_value.setText(
                "始终启用" if item.hard_protection_enabled else "未报告/旧协议"
            )
            idle_and_unlocked = item.state == 0 and not item.locked
            self.control_panel.set_editable(idle_and_unlocked)
            self.start_button.setEnabled(self._connected and idle_and_unlocked)
            self.stop_button.setEnabled(self._connected)
            self.unlock_button.setEnabled(self._connected and item.locked)
            self._refresh_parameter_editors(item)
            self.connection_value.setText("已连接 · 数据正常")
        elif parsed.kind == "ack" and parsed.ack is not None:
            result = "接受" if parsed.ack.ok else f"拒绝：{parsed.ack.reason}"
            self._append_event("CMD_ACK", f"{parsed.ack.command or '命令'} {result}")
        else:
            detail = parsed.error or parsed.text
            self._append_event(parsed.event_type or parsed.kind.upper(), detail)
        for event in self.controller.events[before:]:
            self._append_event(event.event_type, event.detail)
        for event in self.controller.analysis_events[analysis_before:]:
            self._handle_analysis_event(event)
        self.sample_count_label.setText(
            f"遥测 {self.controller.telemetry_rows} · 丢帧 {self.controller.lost_frames} · "
            f"解析错误 {self.controller.parse_errors}"
        )

    def _append_event(self, event_type: str, detail: str) -> None:
        stamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        self.event_view.append(f"{stamp}  [{event_type}]  {detail}")

    def _change_window(self, text: str) -> None:
        seconds = float(text.split()[0])
        self.controller.plot_buffer = RollingPlotBuffer(window_seconds=seconds)

    def _refresh_plot(self) -> None:
        points = 5 if self.smoothing_box.isChecked() else 1
        snapshot = self.controller.plot_buffer.snapshot(smoothing_points=points)
        self.command_curve.setData(snapshot.time_s, snapshot.command_v)
        self.feedback_curve.setData(snapshot.time_s, snapshot.vreal_v)
        self.left_curve.setData(
            snapshot.time_s, tuple(float(value) for value in snapshot.left_state)
        )

    @staticmethod
    def _select_data(box: QComboBox, value: int) -> None:
        index = box.findData(value)
        if index >= 0:
            box.setCurrentIndex(index)

    def _refresh_parameter_editors(self, item) -> None:
        if item.protocol_version < 6:
            return
        self._select_data(self.control_panel.voltage_box, item.vset_v)
        self.control_panel.waveform_box.setCurrentText(
            "HOLD" if item.waveform == 0 else "SQUARE"
        )
        self._select_data(self.control_panel.period_box, item.period_ms)
        self._select_data(self.control_panel.duty_box, item.duty_pct)
        self._select_data(self.control_panel.phase_box, item.phase_deg)
        self._select_data(self.control_panel.duration_box, item.run_duration_ms)
        self.control_panel.clear_box.setChecked(bool(item.end_clear))

    def _send_command(self, command: BoardCommand) -> None:
        if not self._connected or self._serial_worker is None:
            self._append_event("CMD_NOT_SENT", "串口未连接")
            return
        try:
            self._serial_worker.write_command(command)
        except Exception as exc:
            self._append_event("CMD_WRITE_ERROR", str(exc))
            return
        self._append_event("CMD_TX", command.text)

    def _confirm_unlock(self) -> None:
        answer = QMessageBox.question(
            self,
            "确认故障解锁",
            "确认现场已安全并完成检查？解锁只返回待机，不会自动重新启动。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._unlock_confirmed()

    def _unlock_confirmed(self) -> None:
        self._send_command(BoardCommand.unlock())
        self.safety.reset_fault_latch()

    def _handle_analysis_event(self, event) -> None:
        actions = self.safety.handle(event)
        self.fault_value.setText(
            f"{event.level.value} · {event.classification} · {event.reason}"
        )
        self._append_event(
            "HV_ANALYSIS",
            f"{event.level.value} {event.classification} {event.reason} "
            f"{event.command_v}->{event.feedback_v} V",
        )
        if actions.send_fault_stop:
            self._send_command(BoardCommand.fault_stop())
            self.safety_banner.setText(
                "检测到疑似击穿：已请求板端锁定停机，等待 locked=1"
            )
            self.safety_banner.setStyleSheet(
                "background:#5b1d28;color:#ffd5da;padding:7px;border-radius:5px;"
            )

    def _on_auto_stop_toggled(self, enabled: bool) -> None:
        latest = self.controller.latest
        board_idle = latest is not None and latest.state == 0 and not latest.locked
        if not enabled:
            answer = QMessageBox.warning(
                self,
                "关闭疑似击穿自动停机",
                "关闭后上位机仍记录和报警，但不会自动发出锁定停机。"
                "板端硬保护不受影响。确认关闭？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            confirmed = answer == QMessageBox.Yes
            try:
                self.safety.set_enabled(
                    False, board_idle=board_idle, confirmed=confirmed
                )
            except PermissionError as exc:
                self.diagnostic_panel.auto_stop_box.blockSignals(True)
                self.diagnostic_panel.auto_stop_box.setChecked(True)
                self.diagnostic_panel.auto_stop_box.blockSignals(False)
                self._append_event("SAFETY", str(exc))
        else:
            self.safety.set_enabled(True, board_idle=board_idle, confirmed=True)
        self._update_safety_banner()

    def _update_safety_banner(self) -> None:
        if self.safety.suspect_auto_stop_enabled:
            self.safety_banner.setText(
                "疑似击穿自动停机：已开启（仅上位机连接时有效；板端硬保护始终独立启用）"
            )
            self.safety_banner.setStyleSheet(
                "background:#183d36;color:#8ff0cf;padding:7px;border-radius:5px;"
            )
        else:
            self.safety_banner.setText(
                "注意：疑似击穿自动停机已关闭；仅记录/报警，板端硬保护仍启用"
            )
            self.safety_banner.setStyleSheet(
                "background:#554512;color:#ffe59a;padding:7px;border-radius:5px;"
            )
        self.right_curve.setData(
            snapshot.time_s,
            tuple(float(value) + 1.1 for value in snapshot.right_state),
        )
        if snapshot.time_s:
            window = float(self.window_seconds_box.currentText().split()[0])
            right = snapshot.time_s[-1]
            self.plot.setXRange(max(0.0, right - window), max(window, right), padding=0)

    def choose_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "选择记录根目录", self.output_dir_edit.text()
        )
        if selected:
            self.output_dir_edit.setText(selected)

    def start_recording(self) -> None:
        if not self._connected:
            QMessageBox.warning(self, "尚未连接", "请先连接驱动板串口。")
            return
        try:
            latest = self.controller.latest
            protocol_version = latest.protocol_version if latest is not None else 3
            run_duration_ms = latest.run_duration_ms if latest is not None else 20000
            duration_inferred = (
                latest.run_duration_inferred if latest is not None else True
            )
            session_dir = self.controller.start_recording(
                Path(self.output_dir_edit.text()),
                {
                    "port": self.port_box.currentData(),
                    "baud": 115200,
                    "telemetry_rate_hz": 50,
                    "protocol_version": protocol_version,
                    "selected_run_duration_ms": run_duration_ms,
                    "duration_inferred": duration_inferred,
                    "suspect_auto_stop": self.safety.suspect_auto_stop_enabled,
                    "feedback_note": "Vreal is board ADC magnitude; left/right and phase are commanded board states.",
                },
            )
        except Exception as exc:
            QMessageBox.critical(self, "无法开始记录", str(exc))
            return
        self.start_record_button.setEnabled(False)
        self.stop_record_button.setEnabled(True)
        self.record_status.setText(f"记录中：{session_dir}")
        self._append_event("RECORD_START", str(session_dir))

    def stop_recording(self) -> None:
        session_dir = self.controller.stop_recording("manual")
        if session_dir is None:
            return
        self.start_record_button.setEnabled(self._connected)
        self.stop_record_button.setEnabled(False)
        self.record_status.setText(f"已封存：{session_dir}")
        self._append_event("RECORD_STOP", str(session_dir))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.is_recording:
            self.controller.stop_recording("window_closed")
        if self._serial_worker is not None and hasattr(
            self._serial_worker, "request_stop"
        ):
            self._serial_worker.request_stop()
        if self._serial_thread is not None:
            self._serial_thread.quit()
            self._serial_thread.wait(1000)
        event.accept()
