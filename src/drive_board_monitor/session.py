"""Connection-independent experiment session state."""

from __future__ import annotations

from pathlib import Path

from .buffer import RollingPlotBuffer
from .fault_detection import FaultDetector, FaultEvent
from .models import ParsedSerialLine, ReceivedSerialLine, StreamEvent, Telemetry
from .protocol import SequenceTracker, parse_serial_line
from .recorder import SessionRecorder


class SessionController:
    def __init__(self, window_seconds: float = 30.0) -> None:
        self.latest: Telemetry | None = None
        self.plot_buffer = RollingPlotBuffer(window_seconds=window_seconds)
        self.events: list[StreamEvent] = []
        self.analysis_events: list[FaultEvent] = []
        self.telemetry_rows = 0
        self.parse_errors = 0
        self.unknown_lines = 0
        self.lost_frames = 0
        self._sequence = SequenceTracker()
        self._recorder: SessionRecorder | None = None
        self._fault_detector = FaultDetector()
        self._last_flush_ns: int | None = None

    @property
    def is_recording(self) -> bool:
        return self._recorder is not None

    @property
    def session_dir(self) -> Path | None:
        return self._recorder.session_dir if self._recorder else None

    def start_recording(self, base_dir: Path, metadata: dict) -> Path:
        if self._recorder is not None:
            raise RuntimeError("a recording is already active")
        self._recorder = SessionRecorder(base_dir, metadata)
        self._last_flush_ns = None
        return self._recorder.session_dir

    def stop_recording(self, reason: str = "manual") -> Path | None:
        if self._recorder is None:
            return None
        session_dir = self._recorder.session_dir
        self._recorder.stop(reason)
        self._recorder = None
        self._last_flush_ns = None
        return session_dir

    def _record_stream_event(
        self, event: StreamEvent, received: ReceivedSerialLine
    ) -> None:
        self.events.append(event)
        if event.lost_frames:
            self.lost_frames += event.lost_frames
        if self._recorder is not None:
            self._recorder.add_system_event(
                event.event_type,
                event.detail,
                received.pc_wall_time_iso,
                received.pc_monotonic_ns,
            )
            if event.lost_frames:
                self._recorder.add_lost_frames(event.lost_frames)

    def process(self, received: ReceivedSerialLine) -> ParsedSerialLine:
        parsed = parse_serial_line(
            received.raw,
            received.pc_wall_time_iso,
            received.pc_monotonic_ns,
        )
        if self._recorder is not None:
            self._recorder.record(received.raw, parsed)

        if parsed.kind == "telemetry" and parsed.telemetry is not None:
            item = parsed.telemetry
            self.latest = item
            self.telemetry_rows += 1
            if item.output_kind == "DRIVE_SYNC":
                command_signed = item.command_voltage_v
            elif item.output_kind == "CANCEL_SYNC":
                command_signed = -item.command_voltage_v
            else:
                command_signed = 0
            self.plot_buffer.append(
                item.pc_monotonic_ns,
                item.command_voltage_v if item.protocol_version >= 6 else command_signed,
                item.feedback_hv_magnitude_v,
                item.feedback_signed_v,
                item.left_state,
                item.right_state,
            )
            analysis_event = self._fault_detector.observe(item)
            if analysis_event is not None:
                self.analysis_events.append(analysis_event)
                if self._recorder is not None:
                    self._recorder.record_analysis_event(analysis_event)
            for event in self._sequence.observe(item.sequence, item.mcu_tick_ms):
                self._record_stream_event(event, received)
        elif parsed.kind == "malformed":
            self.parse_errors += 1
        elif parsed.kind == "unknown":
            self.unknown_lines += 1

        if self._recorder is not None:
            if self._last_flush_ns is None:
                self._last_flush_ns = received.pc_monotonic_ns
            elif received.pc_monotonic_ns - self._last_flush_ns >= 1_000_000_000:
                self._recorder.flush()
                self._last_flush_ns = received.pc_monotonic_ns
        return parsed

    def connection_lost(
        self, detail: str, wall_time_iso: str, monotonic_ns: int
    ) -> Path | None:
        event = StreamEvent("SERIAL_DISCONNECTED", detail)
        self._fault_detector.reset()
        received = ReceivedSerialLine(b"", wall_time_iso, monotonic_ns)
        self._record_stream_event(event, received)
        return self.stop_recording("serial_disconnected")
