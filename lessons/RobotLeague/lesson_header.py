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
else:
    try:
        myRobot = srv2.bot(base_speed=300, rate_hz=20, verbose=False)
    except Exception as e:
        myRobot = None
        _LOAD_ERRORS["student_robot_v2"] = str(e)

bot = srv2.bot if srv2 is not None else None
robot = myRobot


def show_v2_status():
    print("backend:", lesson_info.get("backend"))
    print("ros_domain_id:", lesson_info.get("ros_domain_id"))
    if srv2 is None:
        print("student_robot_v2: unavailable ->", _LOAD_ERRORS.get("student_robot_v2"))
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
