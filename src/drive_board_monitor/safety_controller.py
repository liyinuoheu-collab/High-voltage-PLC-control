"""Session-scoped policy for the optional PC suspected-arc stop."""

from __future__ import annotations

from dataclasses import dataclass

from .fault_detection import FaultEvent, FaultLevel


@dataclass(frozen=True)
class SafetyActions:
    log: bool
    alert: bool
    send_fault_stop: bool


class SafetyController:
    def __init__(self) -> None:
        self.suspect_auto_stop_enabled = True
        self._fault_stop_sent = False

    def reset_for_connection(self) -> None:
        self.suspect_auto_stop_enabled = True
        self._fault_stop_sent = False

    def reset_fault_latch(self) -> None:
        self._fault_stop_sent = False

    def set_enabled(
        self, enabled: bool, *, board_idle: bool, confirmed: bool = False
    ) -> None:
        if not enabled:
            if not board_idle:
                raise PermissionError("只能在板端待机时关闭疑似击穿自动停机")
            if not confirmed:
                raise PermissionError("关闭自动停机需要明确确认")
        self.suspect_auto_stop_enabled = bool(enabled)
        if enabled:
            self._fault_stop_sent = False

    def handle(self, event: FaultEvent) -> SafetyActions:
        if event.level is not FaultLevel.ARC_SUSPECT:
            return SafetyActions(log=True, alert=False, send_fault_stop=False)
        should_stop = (
            self.suspect_auto_stop_enabled and not self._fault_stop_sent
        )
        if should_stop:
            self._fault_stop_sent = True
        return SafetyActions(log=True, alert=True, send_fault_stop=should_stop)
