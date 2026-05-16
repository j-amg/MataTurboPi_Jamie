#!/usr/bin/env python3
"""
Simulator shim for common/lib/line_follower_lib.py

Imports the real LineFollower and ROSLineFollower classes directly — they work
fine in the simulator because they only depend on:
  - infrared_lib  (shimmed → reads sim_state)
  - robot_moves   (shimmed → updates sim_state)

No extra wrapping needed.  The ROSLineFollower is stubbed out because there
is no ROS node running in simulator mode.

Usage in lessons (backend="sim"):
    from lesson_header import *          # loads the sim shims automatically
    lf = line_pid                        # pre-built LineFollower from lesson_header
    lf.follow_for(3.0)                   # runs in sim

    # To test a specific sensor pattern:
    from simulator.shims.infrared_lib import set_sensor_pattern
    set_sensor_pattern("right")          # robot is left of centre
    info = lf.step()
    print(info)                          # {"states": [...], "error": 2.0, "turn": 0.25, ...}
"""

from __future__ import annotations

# Re-export the real PIDConfig and LineFollower — they are simulator-compatible.
from line_follower_lib import (  # noqa: F401  (re-export)
    LineFollower,
    PIDConfig,
)

# Stub out the ROS-dependent classes so imports don't crash in sim mode.
from ros_service_client import (  # noqa: F401
    clear_process_singleton,
    get_process_singleton,
    set_process_singleton,
)


class ROSLineFollower:
    """Stub — ROS line-following node is not available in simulator mode."""

    def __init__(self, namespace: str = "/line_following"):
        self.ns = namespace

    def _unavailable(self, *_a, **_kw):
        print("[sim] ROSLineFollower is not available in simulator mode. Use LineFollower instead.")
        return None

    ready = enter = exit = set_running = start = stop = _unavailable
    set_threshold = set_target_point = set_color_name = get_target_color = _unavailable


def get_ros_line_follower(namespace: str = "/line_following") -> ROSLineFollower:
    key = "line_follower_lib:ros_client"
    inst = get_process_singleton(key)
    if inst is None:
        inst = set_process_singleton(key, ROSLineFollower(namespace=namespace))
    return inst


def reset_ros_line_follower() -> None:
    key = "line_follower_lib:ros_client"
    inst = get_process_singleton(key)
    if inst is not None:
        try:
            inst.close()  # type: ignore[attr-defined]
        except Exception:
            pass
    clear_process_singleton(key)
