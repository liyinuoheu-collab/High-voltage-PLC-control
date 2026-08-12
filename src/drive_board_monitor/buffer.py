"""Bounded display-only rolling buffer."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class PlotSnapshot:
    time_s: tuple[float, ...]
    vcmd_v: tuple[float, ...]
    vreal_v: tuple[float, ...]
    left_state: tuple[int, ...]
    right_state: tuple[int, ...]

    @property
    def command_v(self) -> tuple[float, ...]:
        return self.vcmd_v

    @property
    def magnitude_v(self) -> tuple[float, ...]:
        return self.vreal_v

    @property
    def signed_v(self) -> tuple[float, ...]:
        return self.vreal_v


def _smooth(values: tuple[float, ...], points: int) -> tuple[float, ...]:
    if points <= 1:
        return values
    result: list[float] = []
    running = 0.0
    window: deque[float] = deque()
    for value in values:
        window.append(value)
        running += value
        if len(window) > points:
            running -= window.popleft()
        result.append(running / points)
    return tuple(result)


class RollingPlotBuffer:
    def __init__(self, window_seconds: float = 30.0, max_points: int = 10000) -> None:
        self.window_ns = int(window_seconds * 1_000_000_000)
        self.max_points = max_points
        self._rows: deque[tuple[int, float, float, int, int]] = deque()
        self._origin_ns: int | None = None

    def append(
        self,
        monotonic_ns: int,
        command_v: float,
        magnitude_v: float,
        signed_v: float,
        left_state: int = 0,
        right_state: int = 0,
    ) -> None:
        if self._origin_ns is None:
            self._origin_ns = monotonic_ns
        self._rows.append(
            (monotonic_ns, command_v, magnitude_v, int(left_state), int(right_state))
        )
        cutoff = monotonic_ns - self.window_ns
        while self._rows and self._rows[0][0] < cutoff:
            self._rows.popleft()
        while len(self._rows) > self.max_points:
            self._rows.popleft()

    def clear(self) -> None:
        self._rows.clear()
        self._origin_ns = None

    def snapshot(self, smoothing_points: int = 1) -> PlotSnapshot:
        if not self._rows or self._origin_ns is None:
            return PlotSnapshot((), (), (), (), ())
        time_s = tuple((row[0] - self._origin_ns) / 1_000_000_000 for row in self._rows)
        command = tuple(row[1] for row in self._rows)
        magnitude = tuple(row[2] for row in self._rows)
        left = tuple(row[3] for row in self._rows)
        right = tuple(row[4] for row in self._rows)
        return PlotSnapshot(
            time_s,
            _smooth(command, smoothing_points),
            _smooth(magnitude, smoothing_points),
            left,
            right,
        )
