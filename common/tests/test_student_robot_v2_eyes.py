import importlib.util
import sys
import types
from pathlib import Path


def _install_support_modules():
    svc_mod = types.ModuleType("ros_service_client")
    svc_mod.clear_process_singleton = lambda *_a, **_k: None
    svc_mod.get_process_singleton = lambda *_a, **_k: None
    svc_mod.set_process_singleton = lambda *_a, **_k: None
    sys.modules["ros_service_client"] = svc_mod

    moves_mod = types.ModuleType("robot_moves")
    moves_mod.forward = lambda **_k: None
    sys.modules["robot_moves"] = moves_mod

    anim_mod = types.ModuleType("student_animation_lib")

    class _Anim:
        def __init__(self):
            self.eye_colours = []

        def set_eye_color(self, rgb):
            self.eye_colours.append(tuple(rgb))

        def start_blinking(self, **_kwargs):
            return None

        def blink_once(self, **_kwargs):
            return None

        def stop_blinking(self):
            return None

        def wink(self, **_kwargs):
            return None

    anim_mod._last = None

    def _get_animation_lib(**_kwargs):
        anim_mod._last = _Anim()
        return anim_mod._last

    anim_mod.get_animation_lib = _get_animation_lib
    sys.modules["student_animation_lib"] = anim_mod

    eyes_mod = types.ModuleType("eyes_lib")

    class _EyesBackend:
        def __init__(self):
            self.calls = []

        def set_both(self, r, g, b):
            self.calls.append(("set_both", int(r), int(g), int(b)))

        def off(self):
            self.calls.append(("off",))

    eyes_mod._backend = None

    def _get_eyes(force_reset=False):
        if force_reset or eyes_mod._backend is None:
            eyes_mod._backend = _EyesBackend()
        return eyes_mod._backend

    eyes_mod.get_eyes = _get_eyes
    sys.modules["eyes_lib"] = eyes_mod
    return anim_mod, eyes_mod


def _load_student_robot_v2():
    path = Path(__file__).resolve().parents[1] / "lib" / "student_robot_v2.py"
    spec = importlib.util.spec_from_file_location("student_robot_v2_for_test", str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v2_eyes_namespace_uses_eyes_lib_backend():
    anim_mod, eyes_mod = _install_support_modules()
    student_robot_v2 = _load_student_robot_v2()

    robot = student_robot_v2.RobotV2(verbose=False)
    robot.eyes.set_both(9, 8, 7)

    backend = eyes_mod._backend
    assert backend is not None
    assert backend.calls == [("set_both", 9, 8, 7)]
    assert anim_mod._last is not None
    assert anim_mod._last.eye_colours[-1] == (9, 8, 7)
