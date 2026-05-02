#!/usr/bin/env python3
# robot_moves.py — classic moves + diagonals (wheel-level) + cmd_vel drifts + horn

from typing import List, Tuple, Optional
import os, sys, time, atexit, subprocess
from pathlib import Path

# ------------------------- Motor controller API (yours) ------------------------
from robot_controller_api import enable_motors, stream_speeds, all_stop

# ---------------------------- Calibration / settings ---------------------------
# Wheel order: FL, FR, RL, RR (matches your controller)
WHEEL_IDS: List[int] = [1, 2, 3, 4]
# Keep your calibrated signs
SIGN: List[int] = [-1, 1, -1, 1]

BASE_SPEED: float = 300.0
RATE_HZ:    float = 20.0

def set_base_speed(speed: float):  # seconds-first API kept the same
    global BASE_SPEED; BASE_SPEED = float(speed)

def set_rate(hz: float):
    global RATE_HZ; RATE_HZ = float(hz)

# ----------------------------- Utils / logging --------------------------------
def _log(*a): print("[robot_moves]", *a, file=sys.stderr, flush=True)

# ----------------------------- Low-level helpers ------------------------------
def _pairs_from4(a: float, b: float, c: float, d: float) -> List[Tuple[int, float]]:
    return [
        (WHEEL_IDS[0], SIGN[0]*float(a)),
        (WHEEL_IDS[1], SIGN[1]*float(b)),
        (WHEEL_IDS[2], SIGN[2]*float(c)),
        (WHEEL_IDS[3], SIGN[3]*float(d)),
    ]

def _spam(a: float, b: float, c: float, d: float, seconds: float):
    enable_motors(True)
    stream_speeds(_pairs_from4(a,b,c,d), seconds=seconds, rate_hz=RATE_HZ)

def stop(): all_stop(WHEEL_IDS)
def emergency_stop(): stop()

# ------------------------------- Classic moves --------------------------------
def forward(seconds: float = 0.5, speed: float = BASE_SPEED):
    s = float(speed); _spam(+s, +s, +s, +s, seconds)

def backward(seconds: float = 0.5, speed: float = BASE_SPEED):
    s = float(speed); _spam(-s, -s, -s, -s, seconds)

def turn_left(seconds: float = 0.5, speed: float = BASE_SPEED):
    s = float(speed); _spam(-s, +s, -s, +s, seconds)

def turn_right(seconds: float = 0.5, speed: float = BASE_SPEED):
    s = float(speed); _spam(+s, -s, +s, -s, seconds)

def left(seconds: float = 0.5, speed: float = BASE_SPEED):
    s = float(speed); _spam(-s, +s, +s, -s, seconds)

def right(seconds: float = 0.5, speed: float = BASE_SPEED):
    s = float(speed); _spam(+s, -s, -s, +s, seconds)

# --------------------------------- Diagonals ----------------------------------
def diagonal_left(seconds: float = 0.8, speed: float = BASE_SPEED):
    s = float(speed); _spam(+s, 0.0, 0.0, +s, seconds)   # FL + RR

def diagonal_right(seconds: float = 0.8, speed: float = BASE_SPEED):
    s = float(speed); _spam(0.0, +s, +s, 0.0, seconds)   # FR + RL

# ----------------------------- /cmd_vel drifting ------------------------------
# Vendor values; tweak via env if needed.
_DRIFT_TOPIC    = os.environ.get("DRIFT_TOPIC", "/cmd_vel")
_DRIFT_RATE_HZ  = float(os.environ.get("DRIFT_RATE_HZ", "20"))
_DRIFT_GAP      = float(os.environ.get("DRIFT_GAP", "0.15"))
_DRIFT_VY_LEFT  = float(os.environ.get("DRIFT_VY_LEFT",  "-0.2"))
_DRIFT_WZ_LEFT  = float(os.environ.get("DRIFT_WZ_LEFT",   "0.5"))
_DRIFT_VY_RIGHT = float(os.environ.get("DRIFT_VY_RIGHT",  "0.2"))
_DRIFT_WZ_RIGHT = float(os.environ.get("DRIFT_WZ_RIGHT", "-0.5"))

# Optional forward “roll” to make the drift arc travel forward a touch
_DRIFT_VX_BIAS  = float(os.environ.get("DRIFT_VX_BIAS", "0.0"))

# ROS2 publisher (lazy)
_rclpy_ok = False
try:
    import rclpy as _rm_rclpy
    from geometry_msgs.msg import Twist as _rm_Twist
    from rclpy.node import Node as _rm_Node
    _rclpy_ok = True
except Exception as e:
    _log("rclpy not available:", e)

__rm_cmdvel_node = None
__rm_cmdvel_pub  = None

def _ensure_cmdvel():
    if not _rclpy_ok:
        raise RuntimeError("rclpy not available; cannot use /cmd_vel drifting.")
    global __rm_cmdvel_node, __rm_cmdvel_pub
    if __rm_cmdvel_pub is not None:
        return
    if not _rm_rclpy.ok():
        _rm_rclpy.init(args=None)
    # Unique-ish node name to avoid collisions if imported twice
    nodename = f"robot_moves_cmdvel_{os.getpid()}"
    __rm_cmdvel_node = _rm_Node(nodename)
    __rm_cmdvel_pub  = __rm_cmdvel_node.create_publisher(_rm_Twist, _DRIFT_TOPIC, 10)
    _log("cmd_vel publisher on", _DRIFT_TOPIC, "rate", _DRIFT_RATE_HZ)

    def _zero_on_exit():
        try:
            if __rm_cmdvel_pub is not None:
                __rm_cmdvel_pub.publish(_rm_Twist())
        except Exception:
            pass
    atexit.register(_zero_on_exit)

def _require_subscriber():
    subs = __rm_cmdvel_pub.get_subscription_count()
    if subs < 1:
        raise RuntimeError(f"No subscriber on {_DRIFT_TOPIC}. Start your base controller first.")

def _hold_cmdvel(seconds: float, vy: float, wz: float, vx_bias: float = _DRIFT_VX_BIAS):
    _ensure_cmdvel()
    _require_subscriber()
    end = time.time() + float(seconds)
    dt  = 1.0 / float(_DRIFT_RATE_HZ)
    while time.time() < end:
        msg = _rm_Twist()
        msg.linear.x  = float(vx_bias)
        msg.linear.y  = float(vy)
        msg.angular.z = float(wz)
        __rm_cmdvel_pub.publish(msg)
        time.sleep(dt)
    __rm_cmdvel_pub.publish(_rm_Twist())
    if _DRIFT_GAP > 0: time.sleep(_DRIFT_GAP)

def drift_left(seconds: float = 1.2, speed: float = BASE_SPEED):
    # speed kept for API symmetry (ignored for /cmd_vel drift)
    _hold_cmdvel(seconds, vy=_DRIFT_VY_LEFT,  wz=_DRIFT_WZ_LEFT)

def drift_right(seconds: float = 1.2, speed: float = BASE_SPEED):
    _hold_cmdvel(seconds, vy=_DRIFT_VY_RIGHT, wz=_DRIFT_WZ_RIGHT)

def drift_demo(cycles: int = 2, per_side_seconds: float = 3.0):
    for _ in range(int(cycles)):
        drift_left(per_side_seconds)
        drift_right(per_side_seconds)

# ------------------------------------ Horn ------------------------------------
HORN_FILE   = os.environ.get("HORN_FILE", "meepmeep.mp3")
HORN_CMD    = os.environ.get("HORN_CMD", "mpg123")
HORN_DEVICE = os.environ.get("HORN_DEVICE")
HORN_DEFAULT_VOLUME = int(os.environ.get("HORN_DEFAULT_VOLUME", "40"))  # 0..100


def _safe_cwd_path() -> Path:
    try:
        p = Path.cwd()
        if p.exists():
            return p
    except Exception:
        pass
    return Path(os.environ.get("HOME", "/tmp"))


_SEARCH_DIRS = [_safe_cwd_path(), Path(__file__).resolve().parent, Path("/opt/sounds"),
                 Path.home()/"Music", Path.home()/"Downloads"]

def _find_horn() -> Optional[Path]:
    p = Path(HORN_FILE).expanduser()
    if p.is_file(): return p
    for d in _SEARCH_DIRS:
        q = d / HORN_FILE
        if q.is_file(): return q
    return None

def _mpg123_scale_from_percent(pct: int) -> int:
    try: p = int(pct)
    except Exception: p = HORN_DEFAULT_VOLUME
    p = max(0, min(100, p))
    return max(1, int(round(32768 * (p / 100.0))))  # 32768 ≈ 100%

def horn(path: Optional[str] = None, device: Optional[str] = HORN_DEVICE,
         volume: Optional[int] = None, block: bool = True) -> bool:
    mp3 = Path(path).expanduser() if path else _find_horn()
    if not mp3 or not mp3.exists():
        print("[horn] can't find", HORN_FILE, "-- set HORN_FILE or pass a path")
        return False
    vol_pct = HORN_DEFAULT_VOLUME if volume is None else int(volume)
    scale = _mpg123_scale_from_percent(vol_pct)
    cmd = [HORN_CMD, "-q", "-f", str(scale)]
    if device: cmd += ["-a", device]
    cmd.append(str(mp3))
    try:
        subprocess.run(cmd, check=True) if block else subprocess.Popen(cmd)
        return True
    except FileNotFoundError:
        print("[horn] mpg123 not found. Install: sudo apt update && sudo apt install -y mpg123 alsa-utils")
        return False
    except Exception as e:
        print("[horn] play failed:", e)
        return False

def Horn(): return horn()
