#!/usr/bin/env python3
"""
Ultrasonic / sonar helper built on the same ROS topic used by the app nodes.
"""
__version__ = "1.1.0"


import os
import threading
import time
from collections import deque
from statistics import mean, stdev
from typing import Deque, List, Optional
from ros_service_client import clear_process_singleton, get_process_singleton, set_process_singleton

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from std_msgs.msg import Int32
except Exception as e:  # pragma: no cover - depends on robot runtime
    rclpy = None
    SingleThreadedExecutor = None
    Node = object  # type: ignore[assignment]
    Int32 = None
    _SONAR_IMPORT_ERROR = e
else:
    _SONAR_IMPORT_ERROR = None


DEFAULT_TOPIC = os.environ.get("SONAR_TOPIC", "/sonar_controller/get_distance").strip() or "/sonar_controller/get_distance"

# Outlier rejection: readings more than this many std-devs from the window mean
# are discarded before averaging.  1.5 removes spikes while keeping valid data.
_OUTLIER_SIGMA = float(os.environ.get("SONAR_OUTLIER_SIGMA", "1.5"))


def _filtered_mean(samples: List[int]) -> float:
    """
    Return a robust mean of sonar samples with outlier rejection.

    Steps (mirrors Hiwonder's avoidance approach):
      1. With ≤ 2 samples, use simple mean (not enough data to detect outliers).
      2. Calculate window mean and std dev.
      3. Discard any sample more than _OUTLIER_SIGMA std-devs from the mean.
      4. Average the survivors; fall back to simple mean if all are rejected.
    """
    if len(samples) <= 2:
        return mean(samples)
    mu = mean(samples)
    sigma = stdev(samples)
    if sigma == 0.0:
        return mu  # all identical — no outliers possible
    survivors = [v for v in samples if abs(v - mu) <= _OUTLIER_SIGMA * sigma]
    return mean(survivors) if survivors else mu


def _require_runtime() -> None:
    if _SONAR_IMPORT_ERROR is not None or rclpy is None or Int32 is None:
        raise RuntimeError(f"ROS sonar dependencies are not available: {_SONAR_IMPORT_ERROR}")


def _rclpy_init_once() -> None:
    _require_runtime()
    if not rclpy.ok():
        rclpy.init(args=None)


class Sonar(Node):
    def __init__(
        self,
        topic: str = DEFAULT_TOPIC,
        window: int = 5,
        node_name: str = "sonar_distance_client",
    ):
        _rclpy_init_once()
        uniq = f"{node_name}_{os.getpid()}_{int(time.time() * 1000) % 100000}"
        super().__init__(uniq)
        self.topic = str(topic)
        self.window = max(1, int(window))
        self._last_mm: Optional[int] = None
        self._last_at: Optional[float] = None
        self._samples: Deque[int] = deque(maxlen=self.window)

        self.create_subscription(Int32, self.topic, self._distance_callback, 10)

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self)
        self._spin_stop = threading.Event()
        self._spin_thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._spin_thread.start()

    def _spin_loop(self) -> None:
        while not self._spin_stop.is_set():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception:
                time.sleep(0.05)

    def close(self) -> None:
        self._spin_stop.set()
        try:
            self._executor.remove_node(self)
        except Exception:
            pass
        try:
            self.destroy_node()
        except Exception:
            pass

    def _distance_callback(self, msg: Int32) -> None:
        value = int(msg.data)
        self._last_mm = value
        self._last_at = time.time()
        self._samples.append(value)

    def has_reading(self) -> bool:
        return self._last_mm is not None

    def wait_for_reading(self, timeout_s: float = 2.0) -> int:
        end = time.time() + float(timeout_s)
        while time.time() < end:
            if self._last_mm is not None:
                return int(self._last_mm)
            time.sleep(0.02)
        raise TimeoutError(f"No sonar reading received from {self.topic} within {timeout_s}s")

    def get_distance_mm(self, filtered: bool = False) -> int:
        if filtered and self._samples:
            # Use outlier-rejecting mean for improved reliability on noisy hardware.
            return int(round(_filtered_mean(list(self._samples))))
        if self._last_mm is None:
            return 0
        return int(self._last_mm)

    def get_distance_cm(self, filtered: bool = False) -> int:
        value = self.get_distance_mm(filtered=filtered)
        return int(round(float(value) / 10.0))

    def is_closer_than(self, threshold_cm: float, filtered: bool = True) -> bool:
        if not self.has_reading():
            return False
        value = self.get_distance_cm(filtered=filtered)
        return bool(value <= float(threshold_cm))

    @property
    def last_update_age_s(self) -> Optional[float]:
        if self._last_at is None:
            return None
        return max(0.0, time.time() - self._last_at)


def get_sonar(topic: str = DEFAULT_TOPIC, window: int = 5) -> Sonar:
    key = "sonar_lib:sonar"
    inst = get_process_singleton(key)
    if inst is None:
        resolved_topic = str(topic or DEFAULT_TOPIC).strip() or DEFAULT_TOPIC
        if not resolved_topic.startswith("/"):
            resolved_topic = f"/{resolved_topic}"
        inst = set_process_singleton(key, Sonar(topic=resolved_topic, window=window))
    return inst


def reset_sonar() -> None:
    key = "sonar_lib:sonar"
    inst = get_process_singleton(key)
    if inst is not None:
        try:
            inst.close()
        except Exception:
            pass
    clear_process_singleton(key)
