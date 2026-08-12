"""Data models shared by parsing, recording, and display layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


MODE_NAMES = {
    0: "持续对照",
    1: "0.2 Hz",
    2: "0.4 Hz",
    3: "0.8 Hz",
    4: "1.6 Hz",
}

MODE_PERIOD_MS = {0: 20000, 1: 5000, 2: 2500, 3: 1250, 4: 625}

STATE_NAMES = {
    0: "待机",
    1: "准备",
    2: "周期驱动",
    3: "抵消前共同态",
    4: "反向电荷抵消",
    5: "关闭前共同态",
    6: "15 s 恢复",
    7: "完成提示",
    8: "急停提示",
}

V6_STATE_NAMES = {
    0: "待机",
    1: "准备",
    2: "驱动",
    3: "路由死区",
    4: "末端清荷",
    5: "15 s 恢复",
    6: "完成提示",
    7: "停机提示",
    8: "故障锁定",
}


@dataclass(frozen=True)
class CommandAck:
    ok: bool
    command: str
    value: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Telemetry:
    pc_wall_time_iso: str
    pc_monotonic_ns: int
    protocol_version: int
    sequence: int
    mcu_tick_ms: int
    run_id: int
    mode: int
    state: int
    phase: int
    cycle: int
    command_voltage_v: int
    feedback_adc_mv: int
    feedback_hv_magnitude_v: int
    end_clear: int
    mode_name: str
    period_ms: int
    state_name: str
    output_kind: str
    feedback_signed_v: int
    run_duration_ms: int
    run_duration_inferred: bool = False
    feedback_polarity_measured: bool = False
    waveform: int = 0
    route: int = 0
    vset_v: int = 0
    duty_pct: int = 0
    phase_deg: int = 0
    left_state: int = 0
    right_state: int = 0
    fault_code: int = 0
    locked: bool = False
    route_stable: bool = False
    hard_protection_enabled: bool = False


@dataclass(frozen=True)
class ParsedSerialLine:
    kind: str
    text: str
    pc_wall_time_iso: str
    pc_monotonic_ns: int
    telemetry: Optional[Telemetry] = None
    ack: Optional[CommandAck] = None
    event_type: str = ""
    error: str = ""


@dataclass(frozen=True)
class StreamEvent:
    event_type: str
    detail: str
    lost_frames: int = 0


@dataclass(frozen=True)
class ReceivedSerialLine:
    raw: bytes
    pc_wall_time_iso: str
    pc_monotonic_ns: int
