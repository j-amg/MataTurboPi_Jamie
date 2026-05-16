#!/usr/bin/env python3
"""
Simulator shim for common/lib/infrared_lib.py

The physical IR sensor reads 4 boolean channels via I2C.  In the simulator
there is no real sensor, so readings come from the sim_state "infrared" dict.

Default state: [False, False, False, False] — robot sees no line.

Students can set specific patterns for unit-testing their line-following logic
without needing real hardware:

    from simulator.core.sim_state import load_state, save_state
    st = load_state()
    st["infrared"]["sensors"] = [False, True, True, False]   # centred on line
    save_state(st)
    # ... run your step() or follow_for() ...

Or use the helper set_sensor_pattern() provided below.
"""

from __future__ import annotations

from typing import List, Optional

from simulator.core.sim_state import load_state, save_state


class Infrared:
    def __init__(self, bus_num: int = 1, address: int = 0x78, register: int = 0x01):
        self.bus_num = int(bus_num)
        self.address = int(address)
        self.register = int(register)

    def close(self) -> None:
        pass  # No resource to release in sim

    def read(self, retries: int = 4, retry_delay_s: float = 0.02) -> List[bool]:
        """Return the current sensor pattern from sim_state."""
        raw = load_state().get("infrared", {}).get("sensors", [False, False, False, False])
        # Coerce to exactly 4 booleans
        padded = list(raw) + [False] * 4
        return [bool(padded[i]) for i in range(4)]

    def read_raw(self, retries: int = 4, retry_delay_s: float = 0.02) -> int:
        """Return the packed byte representation of the current sensor pattern."""
        states = self.read()
        value = 0
        for i, s in enumerate(states):
            if s:
                value |= (1 << i)
        return value

    def scan_i2c_bus(self) -> List[str]:
        """No I2C bus in the simulator — return a placeholder."""
        return [hex(self.address)]


_IR_SINGLETON: Optional[Infrared] = None


def get_infrared(bus_num: int = 1, address: int = 0x78, register: int = 0x01) -> Infrared:
    global _IR_SINGLETON
    if _IR_SINGLETON is None:
        _IR_SINGLETON = Infrared(bus_num=bus_num, address=address, register=register)
    return _IR_SINGLETON


def reset_infrared() -> None:
    global _IR_SINGLETON
    _IR_SINGLETON = None


# ---------------------------------------------------------------------------
# Test helpers — set IR sensor patterns without touching sim_state directly
# ---------------------------------------------------------------------------

_NAMED_PATTERNS = {
    "none":          [False, False, False, False],  # line lost
    "centre":        [False, True,  True,  False],  # on centre
    "left":          [True,  True,  False, False],  # drifted right, sensors see left
    "right":         [False, False, True,  True ],  # drifted left, sensors see right
    "far_left":      [True,  False, False, False],  # hard left
    "far_right":     [False, False, False, True ],  # hard right
    "junction":      [True,  True,  True,  True ],  # T-junction / solid block
}


def set_sensor_pattern(pattern) -> None:
    """
    Set the IR sensor state for simulator testing.

    Args:
        pattern: A named string key from the table below, or a 4-element list
                 of booleans e.g. [False, True, True, False].

    Named patterns:
        "none"       → [F, F, F, F]  line lost
        "centre"     → [F, T, T, F]  robot centred on line
        "left"       → [T, T, F, F]  robot drifted right
        "right"      → [F, F, T, T]  robot drifted left
        "far_left"   → [T, F, F, F]  hard left correction needed
        "far_right"  → [F, F, F, T]  hard right correction needed
        "junction"   → [T, T, T, T]  all sensors on (junction / full stop)

    Example:
        set_sensor_pattern("right")     # test PID corrects leftward drift
        set_sensor_pattern([False, True, True, False])
    """
    if isinstance(pattern, str):
        key = pattern.lower().strip()
        if key not in _NAMED_PATTERNS:
            raise ValueError(f"Unknown pattern '{pattern}'. Choose from: {list(_NAMED_PATTERNS)}")
        sensors = _NAMED_PATTERNS[key]
    else:
        sensors = [bool(v) for v in pattern]
        if len(sensors) != 4:
            raise ValueError(f"Pattern must have exactly 4 elements, got {len(sensors)}")

    st = load_state()
    st["infrared"]["sensors"] = sensors
    save_state(st)
