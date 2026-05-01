__version__ = "1.1.1"

# eyes_lib.py
import atexit
import os
import threading
import time
from typing import List, Optional, Tuple

from ros_robot_controller_msgs.msg import RGBState, RGBStates

ENV_TOPIC = os.getenv("EYES_TOPIC", "").strip()
EYES_BACKEND = os.getenv("EYES_BACKEND", "auto").strip().lower() or "auto"

CANDIDATE_TOPICS = [
    "/sonar_controller/set_rgb",
    "/ros_robot_controller/set_rgb",
]

DEFAULT_INDICES = (0, 1)

# How long to spin after each publish. This is what makes notebooks reliable.
FLUSH_SPIN_S = float(os.getenv("EYES_FLUSH_SPIN_S", "0.15"))
# Optional small pause (usually not needed)
FLUSH_PAUSE_S = float(os.getenv("EYES_FLUSH_PAUSE_S", "0.00"))


def _qos_rel():
    from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

    return QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=10,
    )


def _rclpy_init_once() -> None:
    import rclpy

    if not rclpy.ok():
        rclpy.init(args=None)


def _load_board_backend():
    if EYES_BACKEND == "ros":
        return None, "ros_forced"
    try:
        from fast_sdk.board_sdk import BoardSDK

        board = BoardSDK()
        if not hasattr(board, "set_rgb"):
            return None, "board_missing_set_rgb"
        return board, "board_sdk"
    except Exception as e:
        if EYES_BACKEND == "board":
            raise RuntimeError(f"board_backend_unavailable:{e}") from e
        return None, f"board_unavailable:{e}"


class Eyes:
    """
    Simple RGB eye helper.

    Preferred path:
    - Drive the LEDs directly through BoardSDK.set_rgb(...), which avoids
      per-notebook ROS node flakiness in student kernels.

    Fallback path:
    - Publish ros_robot_controller_msgs/RGBStates to the sonar/controller RGB
      topic and flush a local executor so messages actually go out.
    """

    def __init__(
        self,
        topic: Optional[str] = None,
        indices: Tuple[int, int] = DEFAULT_INDICES,
        node_name: str = "eyes_rgb_client",
    ):
        self.left_i = int(indices[0])
        self.right_i = int(indices[1])
        self.topic = topic or ENV_TOPIC or CANDIDATE_TOPICS[0]
        self.backend_reason = ""
        self._board = None
        self._ros_node = None
        self._exec = None
        self.pub = None

        self._board, self.backend_reason = _load_board_backend()
        if self._board is None:
            self._init_ros_backend(topic=topic, node_name=node_name)
            self.backend = "ros"
        else:
            self.backend = "board"

        self._blink_thread: Optional[threading.Thread] = None
        self._blink_stop = threading.Event()

        atexit.register(self.off)
        print(
            f"eyes_lib ready → backend={self.backend}"
            f" reason={self.backend_reason} topic={self.topic} indices={indices}"
        )

    # ---------- backend setup ----------
    def _init_ros_backend(self, topic: Optional[str], node_name: str) -> None:
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node

        _rclpy_init_once()

        uniq = f"{node_name}_{os.getpid()}_{int(time.time()*1000)%100000}"
        node = Node(uniq)
        self.topic = topic or ENV_TOPIC or self._auto_topic(node)
        self.pub = node.create_publisher(RGBStates, self.topic, _qos_rel())

        executor = SingleThreadedExecutor()
        executor.add_node(node)

        self._ros_node = node
        self._exec = executor

    # ---------- ROS helpers ----------
    def _auto_topic(self, node) -> str:
        try:
            topics = {name for (name, _types) in node.get_topic_names_and_types()}
            for t in CANDIDATE_TOPICS:
                if t in topics:
                    return t
        except Exception:
            pass
        return CANDIDATE_TOPICS[0]

    def _flush(self, seconds: float = FLUSH_SPIN_S) -> None:
        if self._exec is None:
            return
        end = time.time() + float(seconds)
        while time.time() < end:
            self._exec.spin_once(timeout_sec=0.05)
        if FLUSH_PAUSE_S > 0:
            time.sleep(FLUSH_PAUSE_S)

    def diagnose(self) -> None:
        print("Backend:", self.backend)
        print("Backend detail:", self.backend_reason)
        print("Topic in use:", self.topic)
        if self.backend != "ros" or self._ros_node is None:
            return
        topics = self._ros_node.get_topic_names_and_types()
        names = sorted([t[0] for t in topics])
        print("Available RGB-like topics:")
        for n in names:
            if "rgb" in n.lower() or "led" in n.lower() or "sonar" in n.lower():
                print(" -", n)

    # ---------- Publish API ----------
    def _publish_states(self, states: List[RGBState]) -> None:
        if self._board is not None:
            payload = [
                (int(s.index), int(s.red), int(s.green), int(s.blue))
                for s in states
            ]
            self._board.set_rgb(payload)
            return

        msg = RGBStates()
        msg.states = states
        self.pub.publish(msg)
        self._flush()

    def set_both(self, r: int, g: int, b: int) -> None:
        self._publish_states(
            [
                RGBState(index=self.left_i, red=int(r), green=int(g), blue=int(b)),
                RGBState(index=self.right_i, red=int(r), green=int(g), blue=int(b)),
            ]
        )

    def set_left(self, r: int, g: int, b: int) -> None:
        self._publish_states([RGBState(index=self.left_i, red=int(r), green=int(g), blue=int(b))])

    def set_right(self, r: int, g: int, b: int) -> None:
        self._publish_states([RGBState(index=self.right_i, red=int(r), green=int(g), blue=int(b))])

    def set_index(self, idx: int, r: int, g: int, b: int) -> None:
        self._publish_states([RGBState(index=int(idx), red=int(r), green=int(g), blue=int(b))])

    def off(self) -> None:
        try:
            self.set_both(0, 0, 0)
        except Exception:
            pass

    # ---------- Effects ----------
    def blink(self, color=(255, 255, 255), period_s=0.25, duration_s=1.0) -> None:
        end = time.time() + float(duration_s)
        on = True
        while time.time() < end:
            if on:
                self.set_both(*color)
            else:
                self.off()
            on = not on
            time.sleep(float(period_s))
        self.off()

    def scan_indices(
        self,
        start: int = 0,
        end: int = 16,
        color=(0, 0, 255),
        hold_s: float = 0.35,
    ) -> None:
        r, g, b = color
        for i in range(int(start), int(end) + 1):
            self.set_index(i, r, g, b)
            print("lit index", i)
            time.sleep(float(hold_s))
            self.set_index(i, 0, 0, 0)
            time.sleep(0.05)

    def close(self) -> None:
        try:
            self.off()
        except Exception:
            pass
        if self._ros_node is not None:
            try:
                self._ros_node.destroy_node()
            except Exception:
                pass
        self._ros_node = None
        self._exec = None
        self.pub = None
        self._board = None


_EYES_SINGLETON: Optional[Eyes] = None


def reset_eyes() -> None:
    global _EYES_SINGLETON
    inst = _EYES_SINGLETON
    _EYES_SINGLETON = None
    if inst is None:
        return
    try:
        inst.close()
    except Exception:
        pass


def get_eyes(
    topic: Optional[str] = None,
    indices: Tuple[int, int] = DEFAULT_INDICES,
    force_reset: bool = False,
) -> Eyes:
    """
    Singleton eyes instance.
    Use force_reset=True to recreate the backend after a hardware or ROS failure.
    """
    global _EYES_SINGLETON
    if force_reset:
        reset_eyes()
    if _EYES_SINGLETON is None:
        _EYES_SINGLETON = Eyes(topic=topic, indices=indices)
    return _EYES_SINGLETON
