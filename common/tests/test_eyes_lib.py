import importlib.util
import os
import sys
import types
from pathlib import Path


def _install_ros_stubs():
    rclpy_mod = types.ModuleType("rclpy")
    rclpy_mod.ok = lambda: True
    rclpy_mod.init = lambda args=None: None
    sys.modules["rclpy"] = rclpy_mod

    node_mod = types.ModuleType("rclpy.node")

    class _Pub:
        def __init__(self):
            self.published = []

        def publish(self, msg):
            self.published.append(msg)

    class _Node:
        def __init__(self, *_a, **_k):
            self.pub = _Pub()

        def create_publisher(self, *_a, **_k):
            return self.pub

        def get_topic_names_and_types(self):
            return [("/sonar_controller/set_rgb", ["ros_robot_controller_msgs/msg/RGBStates"])]

        def destroy_node(self):
            pass

    node_mod.Node = _Node
    sys.modules["rclpy.node"] = node_mod

    exec_mod = types.ModuleType("rclpy.executors")

    class _Exec:
        def add_node(self, _node):
            pass

        def spin_once(self, timeout_sec=0.0):
            pass

    exec_mod.SingleThreadedExecutor = _Exec
    sys.modules["rclpy.executors"] = exec_mod

    qos_mod = types.ModuleType("rclpy.qos")

    class _QoSProfile:
        def __init__(self, **_kwargs):
            pass

    class _QoSRel:
        RELIABLE = "RELIABLE"

    class _QoSHist:
        KEEP_LAST = "KEEP_LAST"

    qos_mod.QoSProfile = _QoSProfile
    qos_mod.QoSReliabilityPolicy = _QoSRel
    qos_mod.QoSHistoryPolicy = _QoSHist
    sys.modules["rclpy.qos"] = qos_mod

    msg_mod = types.ModuleType("ros_robot_controller_msgs.msg")

    class _RGBState:
        def __init__(self, index=0, red=0, green=0, blue=0):
            self.index = index
            self.red = red
            self.green = green
            self.blue = blue

    class _RGBStates:
        def __init__(self):
            self.states = []

    msg_mod.RGBState = _RGBState
    msg_mod.RGBStates = _RGBStates
    sys.modules["ros_robot_controller_msgs.msg"] = msg_mod


def _install_board_stub():
    fast_sdk_mod = types.ModuleType("fast_sdk")
    board_mod = types.ModuleType("fast_sdk.board_sdk")

    class _BoardSDK:
        def __init__(self):
            self.calls = []

        def set_rgb(self, payload):
            self.calls.append(payload)

    board_mod.BoardSDK = _BoardSDK
    sys.modules["fast_sdk"] = fast_sdk_mod
    sys.modules["fast_sdk.board_sdk"] = board_mod


def _clear_optional_modules():
    for name in [
        "fast_sdk",
        "fast_sdk.board_sdk",
        "rclpy",
        "rclpy.node",
        "rclpy.executors",
        "rclpy.qos",
        "ros_robot_controller_msgs.msg",
    ]:
        sys.modules.pop(name, None)


def _load_eyes_lib(monkeypatch, backend="auto", board_available=True):
    _clear_optional_modules()
    _install_ros_stubs()
    if board_available:
        _install_board_stub()
    monkeypatch.setenv("EYES_BACKEND", backend)
    monkeypatch.setenv("EYES_FLUSH_SPIN_S", "0")
    monkeypatch.setenv("EYES_FLUSH_PAUSE_S", "0")

    path = Path(__file__).resolve().parents[1] / "lib" / "eyes_lib.py"
    module_name = f"eyes_lib_for_test_{backend}_{'board' if board_available else 'ros'}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_prefers_board_sdk_when_available(monkeypatch):
    eyes_lib = _load_eyes_lib(monkeypatch, backend="auto", board_available=True)
    eyes = eyes_lib.get_eyes(force_reset=True)

    assert eyes.backend == "board"
    eyes.set_both(1, 2, 3)
    assert eyes._board.calls[-1] == [(0, 1, 2, 3), (1, 1, 2, 3)]


def test_falls_back_to_ros_when_board_unavailable(monkeypatch):
    eyes_lib = _load_eyes_lib(monkeypatch, backend="auto", board_available=False)
    eyes = eyes_lib.get_eyes(force_reset=True)

    assert eyes.backend == "ros"
    eyes.set_left(10, 20, 30)
    pub = eyes.pub
    assert pub is not None
    assert len(pub.published) == 1
    msg = pub.published[0]
    assert [(s.index, s.red, s.green, s.blue) for s in msg.states] == [(0, 10, 20, 30)]
