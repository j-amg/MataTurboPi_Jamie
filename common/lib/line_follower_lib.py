#!/usr/bin/env python3
"""
line_follower_lib.py
Simple PID line following built on Infrared + robot_moves.
"""
__version__ = "1.1.0"


import time
from dataclasses import dataclass
from typing import List, Optional

from infrared_lib import Infrared, get_infrared
from ros_service_client import (
    ROSServiceClient,
    clear_process_singleton,
    get_process_singleton,
    set_process_singleton,
)

try:
    from std_srvs.srv import SetBool, Trigger
    from interfaces.srv import SetFloat64, SetPoint
    from large_models_msgs.srv import SetString
except Exception as e:  # pragma: no cover - depends on robot runtime
    SetBool = None
    Trigger = None
    SetFloat64 = None
    SetPoint = None
    SetString = None
    _ROS_LINE_IMPORT_ERROR = e
else:
    _ROS_LINE_IMPORT_ERROR = None


@dataclass
class PIDConfig:
    kp: float = 25.0
    ki: float = 0.0
    kd: float = 4.0
    integral_limit: float = 100.0


class LineFollower:
    """
    Reads 4 IR sensors and commands robot movement with a PID steering correction.

    Expected sensor bit order: [s0, s1, s2, s3] — left to right.
    Default weights: [-3, -1, +1, +3] — negative = left of centre, positive = right.

    Error is computed as the weighted SUM of active sensor readings (True=1, False=0).
    This is the standard weighted-sensor-fusion approach:
        error = Σ(weight_i * sensor_i)
    Max possible error with default weights: ±4 (all left or all right sensors on).
    Typical single-sensor range: ±1 or ±3.

    Steering uses yaw (angular_rate), not lateral strafe. The robot turns its heading
    to re-align with the line rather than sliding sideways past it.

    Junction detection:
        All 4 sensors on → the robot has hit a T-junction or solid block.
        junction_action controls the response: "stop" (default) or "continue".
    """

    def __init__(
        self,
        infrared: Optional[Infrared] = None,
        base_speed: float = 220.0,
        weights: Optional[List[float]] = None,
        pid: Optional[PIDConfig] = None,
        max_turn: float = 0.8,
        junction_action: str = "stop",
    ):
        self.ir = infrared if infrared is not None else get_infrared()
        self.base_speed = float(base_speed)
        self.weights = weights if weights is not None else [-3.0, -1.0, 1.0, 3.0]
        self.pid = pid if pid is not None else PIDConfig()
        self.max_turn = float(max_turn)
        self.junction_action = str(junction_action)  # "stop" | "continue"

        self._integral = 0.0
        self._prev_error = 0.0
        self._last_time = None
        self.at_junction = False

        import robot_moves as rm

        self.rm = rm

    def _calc_error(self, states: List[bool]) -> float:
        """
        Weighted SUM of sensor readings.

        Each sensor contributes weight_i * bool(sensor_i).  Using a sum (not an
        average of active-only sensors) gives a consistent, linear error scale
        regardless of how many sensors are over the line — making PID gain tuning
        predictable.  When no sensors are active (line lost) we hold the last
        known error so the robot keeps turning in the last-corrected direction.
        """
        if len(states) != len(self.weights):
            raise ValueError(f"Expected {len(self.weights)} sensor states, got {len(states)}")
        error = float(sum(w * int(bool(s)) for w, s in zip(self.weights, states)))
        if error == 0.0 and not any(states):
            # Line lost — hold last error so robot keeps turning toward line.
            return self._prev_error
        return error

    def _is_junction(self, states: List[bool]) -> bool:
        """All sensors on indicates a T-junction, solid block, or robot being lifted."""
        return all(bool(s) for s in states)

    def _pid_turn(self, error: float) -> float:
        now = time.time()
        dt = 0.02 if self._last_time is None else max(1e-3, now - self._last_time)
        self._last_time = now

        self._integral += error * dt
        lim = abs(float(self.pid.integral_limit))
        self._integral = max(-lim, min(lim, self._integral))

        deriv = (error - self._prev_error) / dt
        self._prev_error = error

        u = self.pid.kp * error + self.pid.ki * self._integral + self.pid.kd * deriv
        # Normalise to [-max_turn, +max_turn].
        # Divisor 200 keeps gains in a human-readable range for notebook tuning.
        # With default weights (max error ≈ ±4) and kp=25: max u = 100 → turn = 0.5
        turn = u / 200.0
        return max(-self.max_turn, min(self.max_turn, turn))

    def step(self, seconds: float = 0.05, speed: Optional[float] = None) -> dict:
        """
        One control step:
          1. Read 4 IR sensors
          2. Detect junction (all on) — stop or continue per junction_action
          3. Compute weighted-sum error
          4. Run PID → angular_rate correction
          5. Command set_velocity(forward + yaw correction)

        Returns a debug dict suitable for logging / Jupyter display:
            {"states": [...], "error": float, "turn": float, "speed": float,
             "junction": bool}
        """
        states = self.ir.read()

        # Junction detection
        self.at_junction = self._is_junction(states)
        if self.at_junction and self.junction_action == "stop":
            self.rm.stop()
            return {
                "states": states,
                "error": 0.0,
                "turn": 0.0,
                "speed": 0.0,
                "junction": True,
            }

        error = self._calc_error(states)
        turn = self._pid_turn(error)
        v = self.base_speed if speed is None else float(speed)

        # Yaw-based steering: robot turns its heading to follow the line.
        # direction_deg=90 → always moving forward; angular_rate=turn rotates chassis.
        # Positive turn → yaw right (line is right of centre).
        self.rm.set_velocity(
            speed=v,
            direction_deg=90.0,
            angular_rate=float(turn),
            seconds=float(seconds),
        )
        return {
            "states": states,
            "error": error,
            "turn": turn,
            "speed": v,
            "junction": False,
        }

    def follow_for(
        self,
        duration_s: float = 3.0,
        step_s: float = 0.05,
        speed: Optional[float] = None,
        stop_at_junction: Optional[bool] = None,
    ) -> bool:
        """
        Run the line-follower control loop for up to duration_s seconds.

        Args:
            stop_at_junction: Override junction_action for this run only.
                              True = stop when junction detected (returns True).
                              False = continue through junctions.
                              None = use self.junction_action setting.

        Returns:
            True if stopped due to junction, False if timed out.
        """
        if stop_at_junction is not None:
            prev = self.junction_action
            self.junction_action = "stop" if stop_at_junction else "continue"

        end = time.time() + float(duration_s)
        hit_junction = False
        try:
            while time.time() < end:
                info = self.step(seconds=step_s, speed=speed)
                if info.get("junction"):
                    hit_junction = True
                    break
        finally:
            self.rm.stop()
            if stop_at_junction is not None:
                self.junction_action = prev  # type: ignore[possibly-undefined]

        return hit_junction

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = 0.0
        self._last_time = None
        self.at_junction = False


def _require_ros_line_interfaces() -> None:
    if (
        _ROS_LINE_IMPORT_ERROR is not None
        or Trigger is None
        or SetBool is None
        or SetFloat64 is None
        or SetPoint is None
        or SetString is None
    ):
        raise RuntimeError(f"ROS line-following interfaces are not available: {_ROS_LINE_IMPORT_ERROR}")


class ROSLineFollower(ROSServiceClient):
    """
    Client wrapper for the camera-based ROS line_following node.
    Keeps the existing IR-based LineFollower above intact.
    """

    def __init__(self, namespace: str = "/line_following"):
        _require_ros_line_interfaces()
        super().__init__("line_following_client")
        self.ns = str(namespace).rstrip("/")

    def _svc(self, name: str) -> str:
        return f"{self.ns}/{name}"

    def ready(self, timeout_s: float = 2.0) -> bool:
        return self.wait_for_service(self._svc("init_finish"), Trigger, timeout_s=timeout_s)

    def enter(self, timeout_s: float = 3.0):
        return self.call(self._svc("enter"), Trigger, Trigger.Request(), timeout_s=timeout_s)

    def exit(self, timeout_s: float = 3.0):
        return self.call(self._svc("exit"), Trigger, Trigger.Request(), timeout_s=timeout_s)

    def set_running(self, enabled: bool = True, timeout_s: float = 3.0):
        req = SetBool.Request()
        req.data = bool(enabled)
        return self.call(self._svc("set_running"), SetBool, req, timeout_s=timeout_s)

    def start(self, timeout_s: float = 3.0):
        return self.set_running(True, timeout_s=timeout_s)

    def stop(self, timeout_s: float = 3.0):
        return self.set_running(False, timeout_s=timeout_s)

    def set_threshold(self, threshold: float, timeout_s: float = 3.0):
        req = SetFloat64.Request()
        req.data = float(threshold)
        return self.call(self._svc("set_threshold"), SetFloat64, req, timeout_s=timeout_s)

    def set_target_point(self, x_norm: float, y_norm: float, timeout_s: float = 3.0):
        req = SetPoint.Request()
        req.data.x = float(x_norm)
        req.data.y = float(y_norm)
        return self.call(self._svc("set_target_color"), SetPoint, req, timeout_s=timeout_s)

    def set_color_name(self, color_name: str, timeout_s: float = 3.0):
        req = SetString.Request()
        req.data = str(color_name)
        return self.call(self._svc("set_large_model_target_color"), SetString, req, timeout_s=timeout_s)

    def get_target_color(self, timeout_s: float = 3.0):
        return self.call(self._svc("get_target_color"), Trigger, Trigger.Request(), timeout_s=timeout_s)


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
            inst.close()
        except Exception:
            pass
    clear_process_singleton(key)
