"""Crash-tolerant, loss-aware session recording."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .models import ParsedSerialLine, Telemetry


TELEMETRY_COLUMNS = (
    "pc_wall_time_iso",
    "pc_time_hms",
    "pc_monotonic_ns",
    "protocol_version",
    "sequence",
    "mcu_tick_ms",
    "run_id",
    "mode",
    "mode_name",
    "period_ms",
    "state",
    "state_name",
    "phase",
    "cycle",
    "command_voltage_v",
    "feedback_adc_mv",
    "feedback_hv_magnitude_v",
    "end_clear",
    "output_kind",
    "feedback_signed_v",
    "feedback_polarity_measured",
    "run_duration_ms",
    "run_duration_inferred",
    "waveform",
    "route",
    "vset_v",
    "duty_pct",
    "phase_deg",
    "left_state",
    "right_state",
    "fault_code",
    "locked",
    "route_stable",
    "hard_protection_enabled",
    "parse_status",
)
EVENT_COLUMNS = (
    "pc_wall_time_iso",
    "pc_monotonic_ns",
    "event_type",
    "detail",
    "raw_line",
    "board_ms",
    "level",
    "reason",
    "classification",
    "command_v",
    "feedback_v",
    "left_state",
    "right_state",
)
SIMPLE_COLUMNS = (
    "电脑时间",
    "实验阶段",
    "设定电压_V",
    "实际电压_V",
    "相位_deg",
    "左输出",
    "右输出",
    "故障码",
)
SIMPLE_STAGE_NAMES = {
    0: "待机",
    1: "准备",
    2: "周期驱动",
    3: "抵消前共模切换",
    4: "反向电荷抵消",
    5: "关闭前共模切换",
    6: "恢复",
    7: "完成提示",
    8: "急停提示",
}


def _pc_time_hms(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%H:%M:%S.%f")[:-3]
    except ValueError:
        return value


class SessionRecorder:
    def __init__(self, base_dir: Path, metadata: dict) -> None:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
        self.session_dir = Path(base_dir) / f"session_{stamp}_{uuid4().hex[:8]}"
        self.session_dir.mkdir(parents=True, exist_ok=False)
        self._raw = (self.session_dir / "serial_raw.log").open("wb")
        self._telemetry_handle = (self.session_dir / "telemetry_raw.csv").open(
            "w", encoding="utf-8", newline=""
        )
        self._events_handle = (self.session_dir / "events.csv").open(
            "w", encoding="utf-8", newline=""
        )
        self._simple_handle = None
        self._simple = None
        simple_export_status = "active"
        simple_export_error = ""
        try:
            self._simple_handle = (self.session_dir / "simple_export.csv").open(
                "w", encoding="utf-8-sig", newline=""
            )
            self._simple = csv.DictWriter(
                self._simple_handle, fieldnames=SIMPLE_COLUMNS
            )
            self._simple.writeheader()
        except OSError as exc:
            simple_export_status = "error"
            simple_export_error = str(exc)
        self._telemetry = csv.DictWriter(
            self._telemetry_handle, fieldnames=TELEMETRY_COLUMNS
        )
        self._events = csv.DictWriter(self._events_handle, fieldnames=EVENT_COLUMNS)
        self._telemetry.writeheader()
        self._events.writeheader()
        self._closed = False
        self._metadata = {
            "format_version": 2,
            "gui_version": "3.0.0",
            "start_time_iso": datetime.now().astimezone().isoformat(),
            "telemetry_rows": 0,
            "event_rows": 0,
            "parse_errors": 0,
            "unknown_lines": 0,
            "lost_frames": 0,
            "selected_run_duration_ms": None,
            "duration_inferred": None,
            "simple_export_status": simple_export_status,
            "simple_export_error": simple_export_error,
            **metadata,
        }
        self._write_metadata()

    def _write_metadata(self) -> None:
        path = self.session_dir / "metadata.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self._metadata, handle, ensure_ascii=False, indent=2)

    @staticmethod
    def _telemetry_row(item: Telemetry) -> dict:
        row = {
            name: getattr(item, name)
            for name in TELEMETRY_COLUMNS
            if name not in ("pc_time_hms", "parse_status")
        }
        row["pc_time_hms"] = _pc_time_hms(item.pc_wall_time_iso)
        row["feedback_polarity_measured"] = int(item.feedback_polarity_measured)
        row["run_duration_inferred"] = int(item.run_duration_inferred)
        row["parse_status"] = "ok"
        return row

    def _write_simple_row(self, item: Telemetry) -> None:
        if self._simple is None:
            return
        computer_time = _pc_time_hms(item.pc_wall_time_iso)
        self._simple.writerow(
            {
                "电脑时间": computer_time,
                "实验阶段": item.state_name,
                "设定电压_V": (
                    item.vset_v
                    if item.protocol_version >= 6
                    else item.command_voltage_v
                ),
                "实际电压_V": item.feedback_hv_magnitude_v,
                "相位_deg": item.phase_deg if item.protocol_version >= 6 else item.phase,
                "左输出": item.left_state,
                "右输出": item.right_state,
                "故障码": item.fault_code,
            }
        )

    def _disable_simple_export(self, exc: Exception) -> None:
        self._metadata["simple_export_status"] = "error"
        self._metadata["simple_export_error"] = str(exc)
        if self._simple_handle is not None:
            try:
                self._simple_handle.close()
            except OSError:
                pass
        self._simple_handle = None
        self._simple = None

    def record(self, raw: bytes, parsed: ParsedSerialLine) -> None:
        if self._closed:
            raise RuntimeError("session recorder is closed")
        self._raw.write(raw)
        if parsed.kind == "telemetry" and parsed.telemetry is not None:
            item = parsed.telemetry
            self._telemetry.writerow(self._telemetry_row(item))
            self._metadata["telemetry_rows"] += 1
            self._metadata["selected_run_duration_ms"] = item.run_duration_ms
            self._metadata["duration_inferred"] = item.run_duration_inferred
            if self._simple is not None:
                try:
                    self._write_simple_row(item)
                except Exception as exc:
                    self._disable_simple_export(exc)
            return

        if parsed.kind == "malformed":
            self._metadata["parse_errors"] += 1
        elif parsed.kind == "unknown":
            self._metadata["unknown_lines"] += 1
        self._events.writerow(
            {
                "pc_wall_time_iso": parsed.pc_wall_time_iso,
                "pc_monotonic_ns": parsed.pc_monotonic_ns,
                "event_type": parsed.event_type or parsed.kind.upper(),
                "detail": parsed.error,
                "raw_line": parsed.text,
            }
        )
        self._metadata["event_rows"] += 1

    def record_analysis_event(self, event) -> None:
        """Persist a detector event without coupling the recorder to its class."""
        if self._closed:
            return
        self._events.writerow(
            {
                "pc_wall_time_iso": event.pc_wall_time_iso,
                "pc_monotonic_ns": "",
                "event_type": "FAULT_ANALYSIS",
                "detail": f"{event.level.value}:{event.reason}",
                "raw_line": "",
                "board_ms": event.board_ms,
                "level": event.level.value,
                "reason": event.reason,
                "classification": event.classification,
                "command_v": event.command_v,
                "feedback_v": event.feedback_v,
                "left_state": event.left_state,
                "right_state": event.right_state,
            }
        )
        self._metadata["event_rows"] += 1

    def add_system_event(
        self, event_type: str, detail: str, wall_time_iso: str, monotonic_ns: int
    ) -> None:
        if self._closed:
            return
        self._events.writerow(
            {
                "pc_wall_time_iso": wall_time_iso,
                "pc_monotonic_ns": monotonic_ns,
                "event_type": event_type,
                "detail": detail,
                "raw_line": "",
            }
        )
        self._metadata["event_rows"] += 1

    def add_lost_frames(self, count: int) -> None:
        self._metadata["lost_frames"] += count

    def flush(self) -> None:
        if self._closed:
            return
        for handle in (self._raw, self._telemetry_handle, self._events_handle):
            handle.flush()
            os.fsync(handle.fileno())
        if self._simple_handle is not None:
            try:
                self._simple_handle.flush()
                os.fsync(self._simple_handle.fileno())
            except OSError as exc:
                self._disable_simple_export(exc)
        self._write_metadata()

    def stop(self, reason: str) -> None:
        if self._closed:
            return
        self._metadata["end_reason"] = reason
        self._metadata["end_time_iso"] = datetime.now().astimezone().isoformat()
        self.flush()
        self._raw.close()
        self._telemetry_handle.close()
        self._events_handle.close()
        if self._simple_handle is not None:
            try:
                self._simple_handle.close()
                if self._metadata["simple_export_status"] == "active":
                    self._metadata["simple_export_status"] = "ok"
            except OSError as exc:
                self._disable_simple_export(exc)
        self._closed = True
        self._write_metadata()
