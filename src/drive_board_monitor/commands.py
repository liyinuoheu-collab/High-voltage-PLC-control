"""Validated ASCII commands for the Donut-HASEL firmware V6 protocol."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoardCommand:
    text: str

    @property
    def wire(self) -> bytes:
        return (self.text + "\r\n").encode("ascii")

    @classmethod
    def ping(cls) -> "BoardCommand":
        return cls("PING")

    @classmethod
    def get(cls) -> "BoardCommand":
        return cls("GET")

    @classmethod
    def start(cls) -> "BoardCommand":
        return cls("START")

    @classmethod
    def stop(cls) -> "BoardCommand":
        return cls("STOP")

    @classmethod
    def unlock(cls) -> "BoardCommand":
        return cls("UNLOCK")

    @classmethod
    def fault_stop(cls) -> "BoardCommand":
        return cls("FAULT,PC_ARC")

    @classmethod
    def set_voltage(cls, voltage_v: int) -> "BoardCommand":
        if voltage_v not in range(4000, 7001, 500):
            raise ValueError("voltage must be 4000..7000 V in 500 V steps")
        return cls(f"SET,V={voltage_v}")

    @classmethod
    def set_period_ms(cls, period_ms: int) -> "BoardCommand":
        if period_ms not in (5000, 2500, 1250, 625):
            raise ValueError("period must be 5000, 2500, 1250 or 625 ms")
        return cls(f"SET,PERIOD_MS={period_ms}")

    @classmethod
    def set_duty(cls, duty_pct: int) -> "BoardCommand":
        if duty_pct not in (25, 50, 75):
            raise ValueError("duty must be 25, 50 or 75 percent")
        return cls(f"SET,DUTY={duty_pct}")

    @classmethod
    def set_phase(cls, phase_deg: int) -> "BoardCommand":
        if phase_deg not in (0, 90, 180):
            raise ValueError("phase must be 0, 90 or 180 degrees")
        return cls(f"SET,PHASE={phase_deg}")

    @classmethod
    def set_duration(cls, duration_ms: int) -> "BoardCommand":
        if duration_ms not in (0, 10000, 20000, 30000, 60000):
            raise ValueError("duration must be 0, 10, 20, 30 or 60 seconds")
        return cls(f"SET,DURATION_MS={duration_ms}")

    @classmethod
    def set_waveform(cls, waveform: str) -> "BoardCommand":
        normalized = waveform.upper()
        if normalized not in ("HOLD", "SQUARE"):
            raise ValueError("waveform must be HOLD or SQUARE")
        return cls(f"SET,WAVE={normalized}")

    @classmethod
    def set_clear(cls, enabled: bool) -> "BoardCommand":
        return cls(f"SET,CLEAR={int(bool(enabled))}")
