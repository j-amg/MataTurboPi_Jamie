"""Lesson 18 — MediaPipe Vision V2 header. Use in any cell: from lesson_header import *"""

from lesson_loader import setup as _setup
lesson_info = _setup(verbose=False)

import time

_LOAD_ERRORS = {}

try:
    import student_robot_v2 as srv2
except Exception as e:
    srv2 = None
    myRobot = None
    _LOAD_ERRORS["student_robot_v2"] = str(e)
    print(f"\u26a0\ufe0f  student_robot_v2 failed to load: {e}")
    print("    Run show_v2_status() for details, or restart the kernel.")
else:
    try:
        myRobot = srv2.bot(base_speed=300, rate_hz=20, verbose=False)
    except Exception as e:
        myRobot = None
        _LOAD_ERRORS["student_robot_v2"] = str(e)

def _bot_unavailable(*args, **kwargs):
    err = _LOAD_ERRORS.get("student_robot_v2", "unknown error")
    raise ImportError(
        "\n\n  student_robot_v2 failed to load.\n"
        f"  Error: {err}\n\n"
        "  Run show_v2_status() to diagnose, or restart the kernel and re-run cell 1."
    )
bot = getattr(srv2, "bot", None) if srv2 is not None else _bot_unavailable
if bot is None:
    bot = _bot_unavailable
robot = myRobot


def show_v2_status():
    print("backend:", lesson_info.get("backend"))
    print("ros_domain_id:", lesson_info.get("ros_domain_id"))
    bootstrap_info = lesson_info.get("bootstrap") or {}
    print("common_lib:", bootstrap_info.get("COMMON_LIB", "unknown"))
    print("lessons_lib:", bootstrap_info.get("LESSONS_LIB", "unknown"))
    if srv2 is None:
        print("student_robot_v2: FAILED ->", _LOAD_ERRORS.get("student_robot_v2"))
        print("  Tip: check common_lib path above exists and contains student_robot_v2.py")
        return
    print("student_robot_v2:", getattr(srv2, "__version__", "unknown"))
    print("module:", getattr(srv2, "__file__", None))
    if myRobot is not None:
        myRobot.status()
    if _LOAD_ERRORS:
        print("load_errors:")
        for name in sorted(_LOAD_ERRORS):
            print(f" - {name}: {_LOAD_ERRORS[name]}")


def stop_robot():
    try:
        if myRobot is not None:
            myRobot.stop()
    except Exception:
        pass


def show_v2_versions():
    if myRobot is None:
        print("student_robot_v2 unavailable")
        return
    myRobot.show_versions()


def show_mediapipe_v2_status():
    show_v2_status()
