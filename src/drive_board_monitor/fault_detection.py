"""Conservative telemetry-only screening for suspected high-voltage breakdown."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Telemetry


class FaultLevel(Enum):
    NORMAL = "normal"
    TRACKING_WARN = "tracking_warn"
    ARC_SUSPECT = "arc_suspect"


@dataclass(frozen=True)
class FaultThresholds:
    sudden_drop_pct: float = 20.0
    sudden_drop_window_ms: int = 60
    tracking_floor_pct: float = 70.0
    tracking_low_ms: int = 200


@dataclass(frozen=True)
class FaultEvent:
    level: FaultLevel
    reason: str
    classification: str
    pc_wall_time_iso: str
    board_ms: int
    command_v: int
    feedback_v: int
    left_state: int
    right_state: int


class FaultDetector:
    """Screen V6 telemetry while masking intended output-route transitions."""

    def __init__(self, thresholds: FaultThresholds | None = None) -> None:
        self.thresholds = thresholds or FaultThresholds()
        self.reset()

    def reset(self) -> None:
        self._run_id: int | None = None
        self._last_tick: int | None = None
        self._last_feedback: int | None = None
        self._last_command: int | None = None
        self._low_since: int | None = None
        self._tracking_warned = False

    @staticmethod
    def _classification(item: Telemetry) -> str:
        if not item.route_stable:
            return "SWITCHING_SUSPECT"
        if item.left_state != item.right_state:
            return "P2P_GAP_SUSPECT"
        if item.waveform == 0 or (item.left_state and item.right_state):
            return "HV_PATH_SUSPECT"
        return "UNLOCATED_ARC"

    def _event(
        self, item: Telemetry, level: FaultLevel, reason: str
    ) -> FaultEvent:
        return FaultEvent(
            level=level,
            reason=reason,
            classification=self._classification(item),
            pc_wall_time_iso=item.pc_wall_time_iso,
            board_ms=item.mcu_tick_ms,
            command_v=item.command_voltage_v,
            feedback_v=item.feedback_hv_magnitude_v,
            left_state=item.left_state,
            right_state=item.right_state,
        )

    def observe(self, item: Telemetry) -> FaultEvent | None:
        if item.protocol_version < 6:
            return None
        if self._run_id != item.run_id:
            self.reset()
            self._run_id = item.run_id

        active = (
            item.state == 2
            and item.route_stable
            and item.command_voltage_v >= 4000
            and (item.left_state or item.right_state)
        )
        if not active:
            self._last_tick = item.mcu_tick_ms
            self._last_feedback = item.feedback_hv_magnitude_v
            self._last_command = item.command_voltage_v
            self._low_since = None
            self._tracking_warned = False
            return None

        event = None
        if (
            self._last_tick is not None
            and self._last_feedback is not None
            and self._last_command == item.command_voltage_v
            and 0 < item.mcu_tick_ms - self._last_tick <= self.thresholds.sudden_drop_window_ms
            and self._last_feedback >= item.command_voltage_v * 0.7
        ):
            drop_pct = (
                (self._last_feedback - item.feedback_hv_magnitude_v)
                * 100.0
                / max(self._last_feedback, 1)
            )
            if drop_pct >= self.thresholds.sudden_drop_pct:
                event = self._event(item, FaultLevel.ARC_SUSPECT, "sudden_drop")

        floor = item.command_voltage_v * self.thresholds.tracking_floor_pct / 100.0
        if item.feedback_hv_magnitude_v < floor:
            if self._low_since is None:
                self._low_since = item.mcu_tick_ms
            elif (
                not self._tracking_warned
                and item.mcu_tick_ms - self._low_since >= self.thresholds.tracking_low_ms
            ):
                self._tracking_warned = True
                if event is None:
                    event = self._event(
                        item, FaultLevel.TRACKING_WARN, "tracking_low"
                    )
        else:
            self._low_since = None
            self._tracking_warned = False

        self._last_tick = item.mcu_tick_ms
        self._last_feedback = item.feedback_hv_magnitude_v
        self._last_command = item.command_voltage_v
        return event
