"""Parser for the board's read-only line protocol."""

from __future__ import annotations

from .models import (
    CommandAck,
    MODE_NAMES,
    MODE_PERIOD_MS,
    STATE_NAMES,
    V6_STATE_NAMES,
    ParsedSerialLine,
    StreamEvent,
    Telemetry,
)


REQUIRED_FIELDS = (
    "v",
    "s",
    "t",
    "r",
    "m",
    "st",
    "p",
    "c",
    "cmd",
    "adc",
    "hv",
    "clr",
)
EVENT_PREFIXES = {"BOOT", "SELECT", "RUN", "PHASE", "STATE", "EVENT"}
V6_REQUIRED_FIELDS = (
    "v",
    "seq",
    "t_ms",
    "run",
    "wave",
    "mode",
    "state",
    "route",
    "left",
    "right",
    "v_set",
    "v_cmd",
    "v_real",
    "adc_mv",
    "period_ms",
    "duty",
    "phase_deg",
    "duration_ms",
    "clear",
    "cycle",
    "fault",
    "locked",
    "stable",
    "hard_protect",
)


def _parse_command_ack(
    text: str, pc_wall_time_iso: str, pc_monotonic_ns: int
) -> ParsedSerialLine | None:
    tokens = text.split(",")
    try:
        index = tokens.index("CMD")
    except ValueError:
        return None
    if len(tokens) <= index + 2 or tokens[index + 1] not in ("ACK", "ERR"):
        return None
    ok = tokens[index + 1] == "ACK"
    detail = tokens[index + 2]
    return ParsedSerialLine(
        "ack",
        text,
        pc_wall_time_iso,
        pc_monotonic_ns,
        ack=CommandAck(
            ok=ok,
            command=detail if ok else "",
            value="",
            reason="" if ok else detail,
        ),
        event_type="CMD_ACK" if ok else "CMD_ERR",
    )


def _parse_fields(
    text: str, pc_wall_time_iso: str, pc_monotonic_ns: int
) -> tuple[dict[str, str] | None, ParsedSerialLine | None]:
    fields: dict[str, str] = {}
    for item in text.split(",")[1:]:
        if "=" not in item:
            return None, ParsedSerialLine(
                "malformed",
                text,
                pc_wall_time_iso,
                pc_monotonic_ns,
                event_type="MALFORMED",
                error=f"field has no '=': {item}",
            )
        key, value = item.split("=", 1)
        fields[key] = value
    return fields, None


def _parse_v6(
    text: str,
    fields: dict[str, str],
    pc_wall_time_iso: str,
    pc_monotonic_ns: int,
) -> ParsedSerialLine:
    missing = [name for name in V6_REQUIRED_FIELDS if name not in fields]
    if missing:
        return ParsedSerialLine(
            "malformed",
            text,
            pc_wall_time_iso,
            pc_monotonic_ns,
            event_type="MALFORMED",
            error="missing fields: " + ",".join(missing),
        )
    try:
        values = {name: int(fields[name], 10) for name in V6_REQUIRED_FIELDS}
    except ValueError as exc:
        return ParsedSerialLine(
            "malformed",
            text,
            pc_wall_time_iso,
            pc_monotonic_ns,
            event_type="MALFORMED",
            error=f"integer conversion failed: {exc}",
        )
    route_names = {
        0: "OFF",
        1: "DRIVE_SYNC",
        2: "LEFT_HIGH_RIGHT_LOW",
        3: "LEFT_LOW_RIGHT_HIGH",
        4: "COMMON_LOW",
        5: "CANCEL_SYNC",
    }
    item = Telemetry(
        pc_wall_time_iso=pc_wall_time_iso,
        pc_monotonic_ns=pc_monotonic_ns,
        protocol_version=values["v"],
        sequence=values["seq"],
        mcu_tick_ms=values["t_ms"],
        run_id=values["run"],
        mode=values["mode"],
        state=values["state"],
        phase=values["phase_deg"],
        cycle=values["cycle"],
        command_voltage_v=values["v_cmd"],
        feedback_adc_mv=values["adc_mv"],
        feedback_hv_magnitude_v=values["v_real"],
        end_clear=values["clear"],
        mode_name=(
            "HOLD"
            if values["wave"] == 0
            else MODE_NAMES.get(values["mode"], f"未知模式 {values['mode']}")
        ),
        period_ms=values["period_ms"],
        state_name=V6_STATE_NAMES.get(
            values["state"], f"未知状态 {values['state']}"
        ),
        output_kind=route_names.get(values["route"], f"ROUTE_{values['route']}"),
        feedback_signed_v=values["v_real"],
        run_duration_ms=values["duration_ms"],
        waveform=values["wave"],
        route=values["route"],
        vset_v=values["v_set"],
        duty_pct=values["duty"],
        phase_deg=values["phase_deg"],
        left_state=values["left"],
        right_state=values["right"],
        fault_code=values["fault"],
        locked=bool(values["locked"]),
        route_stable=bool(values["stable"]),
        hard_protection_enabled=bool(values["hard_protect"]),
    )
    return ParsedSerialLine(
        "telemetry", text, pc_wall_time_iso, pc_monotonic_ns, telemetry=item
    )


def _output_kind(state: int, phase: int) -> str:
    if state == 2 and phase >= 0:
        return "OFF" if phase % 2 == 0 else "DRIVE_SYNC"
    if state in (3, 5):
        return "COMMON_MODE"
    if state == 4:
        return "CANCEL_SYNC"
    return "OFF"


def _signed_feedback(output_kind: str, magnitude_v: int) -> int:
    if output_kind == "DRIVE_SYNC":
        return magnitude_v
    if output_kind == "CANCEL_SYNC":
        return -magnitude_v
    return 0


def parse_serial_line(
    raw: bytes, pc_wall_time_iso: str, pc_monotonic_ns: int
) -> ParsedSerialLine:
    text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    if not text.startswith("D,"):
        ack = _parse_command_ack(text, pc_wall_time_iso, pc_monotonic_ns)
        if ack is not None:
            return ack
        prefix = text.split(",", 1)[0]
        if prefix in EVENT_PREFIXES:
            return ParsedSerialLine(
                "event", text, pc_wall_time_iso, pc_monotonic_ns, event_type=prefix
            )
        return ParsedSerialLine(
            "unknown", text, pc_wall_time_iso, pc_monotonic_ns, event_type="UNKNOWN"
        )

    fields, error = _parse_fields(text, pc_wall_time_iso, pc_monotonic_ns)
    if error is not None:
        return error
    assert fields is not None
    try:
        version = int(fields.get("v", ""), 10)
    except ValueError:
        version = -1
    if version >= 6:
        return _parse_v6(text, fields, pc_wall_time_iso, pc_monotonic_ns)

    missing = [name for name in REQUIRED_FIELDS if name not in fields]
    if missing:
        return ParsedSerialLine(
            "malformed",
            text,
            pc_wall_time_iso,
            pc_monotonic_ns,
            event_type="MALFORMED",
            error="missing fields: " + ",".join(missing),
        )

    try:
        values = {name: int(fields[name], 10) for name in REQUIRED_FIELDS}
    except ValueError as exc:
        return ParsedSerialLine(
            "malformed",
            text,
            pc_wall_time_iso,
            pc_monotonic_ns,
            event_type="MALFORMED",
            error=f"integer conversion failed: {exc}",
        )

    duration_inferred = values["v"] < 4
    if duration_inferred:
        run_duration_ms = 20000
    else:
        if "dur" not in fields:
            return ParsedSerialLine(
                "malformed",
                text,
                pc_wall_time_iso,
                pc_monotonic_ns,
                event_type="MALFORMED",
                error="missing fields: dur",
            )
        try:
            run_duration_ms = int(fields["dur"], 10)
        except ValueError as exc:
            return ParsedSerialLine(
                "malformed",
                text,
                pc_wall_time_iso,
                pc_monotonic_ns,
                event_type="MALFORMED",
                error=f"integer conversion failed: {exc}",
            )
        if run_duration_ms < 0:
            return ParsedSerialLine(
                "malformed",
                text,
                pc_wall_time_iso,
                pc_monotonic_ns,
                event_type="MALFORMED",
                error="dur must be non-negative",
            )

    output_kind = _output_kind(values["st"], values["p"])
    telemetry = Telemetry(
        pc_wall_time_iso=pc_wall_time_iso,
        pc_monotonic_ns=pc_monotonic_ns,
        protocol_version=values["v"],
        sequence=values["s"],
        mcu_tick_ms=values["t"],
        run_id=values["r"],
        mode=values["m"],
        state=values["st"],
        phase=values["p"],
        cycle=values["c"],
        command_voltage_v=values["cmd"],
        feedback_adc_mv=values["adc"],
        feedback_hv_magnitude_v=values["hv"],
        end_clear=values["clr"],
        mode_name=MODE_NAMES.get(values["m"], f"未知模式 {values['m']}"),
        period_ms=MODE_PERIOD_MS.get(values["m"], 0),
        state_name=STATE_NAMES.get(values["st"], f"未知状态 {values['st']}"),
        output_kind=output_kind,
        feedback_signed_v=_signed_feedback(output_kind, values["hv"]),
        run_duration_ms=run_duration_ms,
        run_duration_inferred=duration_inferred,
    )
    return ParsedSerialLine(
        "telemetry", text, pc_wall_time_iso, pc_monotonic_ns, telemetry=telemetry
    )


class SequenceTracker:
    """Detect lost telemetry and MCU restarts without confusing uint32 wrap."""

    def __init__(self) -> None:
        self._sequence: int | None = None
        self._tick: int | None = None

    def reset(self) -> None:
        self._sequence = None
        self._tick = None

    def observe(self, sequence: int, tick_ms: int) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        if self._sequence is None:
            self._sequence, self._tick = sequence, tick_ms
            return events

        if self._tick is not None and tick_ms < self._tick:
            events.append(StreamEvent("BOARD_RESTART", "MCU tick moved backwards"))
            self._sequence, self._tick = sequence, tick_ms
            return events

        expected = (self._sequence + 1) & 0xFFFFFFFF
        if sequence != expected:
            gap = (sequence - expected) & 0xFFFFFFFF
            if gap < 0x80000000:
                events.append(
                    StreamEvent(
                        "FRAME_GAP", f"lost {gap} telemetry frame(s)", lost_frames=gap
                    )
                )
            else:
                events.append(StreamEvent("SEQUENCE_BACKWARD", "sequence moved backwards"))

        self._sequence, self._tick = sequence, tick_ms
        return events
