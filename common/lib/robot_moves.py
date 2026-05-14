#!/usr/bin/env python3
__version__ = "1.1.0"

# robot_moves.py — direct motor moves + diagonals + wheel-level drift + horn + RobotMoves class
from typing import List, Tuple, Optional
import os, sys, time, subprocess
from pathlib import Path

from robot_controller_api import enable_motors, stream_speeds, all_stop

# Wheel order: FL, FR, RL, RR
WHEEL_IDS: List[int] = [1, 2, 3, 4]

# Your calibrated signs (do not change)
SIGN: List[int] = [-1, 1, -1, 1]

BASE_SPEED: float = float(os.environ.get("BASE_SPEED", "300"))
RATE_HZ: float = float(os.environ.get("RATE_HZ", "20"))

def set_base_speed(speed: float):
    global BASE_SPEED
    BASE_SPEED = float(speed)

def set_rate(hz: float):
    global RATE_HZ
    RATE_HZ = float(hz)

def _log(*a):
    print("[robot_moves]", *a, file=sys.stderr, flush=True)

def _pairs_from4(fl: float, fr: float, rl: float, rr: float) -> List[Tuple[int, float]]:
    return [
        (WHEEL_IDS[0], SIGN[0] * float(fl)),
        (WHEEL_IDS[1], SIGN[1] * float(fr)),
        (WHEEL_IDS[2], SIGN[2] * float(rl)),
        (WHEEL_IDS[3], SIGN[3] * float(rr)),
    ]

def _spam(fl: float, fr: float, rl: float, rr: float, seconds: float):
    enable_motors(True)
    stream_speeds(_pairs_from4(fl, fr, rl, rr), seconds=float(seconds), rate_hz=RATE_HZ)

def stop():
    all_stop(WHEEL_IDS)

def emergency_stop():
    stop()

# ------------------------------- Classic moves --------------------------------
def forward(seconds: float = 0.5, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(+s, +s, +s, +s, seconds)

def backward(seconds: float = 0.5, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(-s, -s, -s, -s, seconds)

def turn_left(seconds: float = 0.5, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(-s, +s, -s, +s, seconds)

def turn_right(seconds: float = 0.5, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(+s, -s, +s, -s, seconds)

def left(seconds: float = 0.5, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(-s, +s, +s, -s, seconds)

def right(seconds: float = 0.5, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(+s, -s, -s, +s, seconds)

# --------------------------------- Diagonals ----------------------------------
def diagonal_left(seconds: float = 0.8, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(+s, 0.0, 0.0, +s, seconds)  # FL + RR

def diagonal_right(seconds: float = 0.8, speed: float = None):
    s = float(BASE_SPEED if speed is None else speed)
    _spam(0.0, +s, +s, 0.0, seconds)  # FR + RL

# ----------------------------- Wheel-level drifting ----------------------------
# Drift is “strafe + a bit of spin” (all motor direct, no /cmd_vel)
_DRIFT_TURN_BLEND = float(os.environ.get("DRIFT_TURN_BLEND", "0.55"))  # 0..1
_DRIFT_SECONDS_DEFAULT = float(os.environ.get("DRIFT_SECONDS_DEFAULT", "1.0"))

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def drift_left(seconds: float = None, speed: float = None, turn_blend: float = None):
    """
    Drift left in an arc.
    turn_blend: 0..1 (0 = pure strafe left, 1 = heavy spin)
    """
    # Classroom-friendly shorthand:
    # drift_left(seconds, 0.55) -> treat 2nd positional as turn_blend.
    if turn_blend is None and speed is not None and -1.0 <= float(speed) <= 1.0:
        turn_blend = float(speed)
        speed = None

    s = float(BASE_SPEED if speed is None else speed)
    t = float(_DRIFT_SECONDS_DEFAULT if seconds is None else seconds)
    k = float(_DRIFT_TURN_BLEND if turn_blend is None else turn_blend)
    k = _clamp(k, 0.0, 1.0)

    # strafe left:   FL-, FR+, RL+, RR-
    # turn left:     FL-, FR+, RL-, RR+
    # combine:       (strafe) + k*(turn)
    fl = (-1.0 - k) * s
    fr = (+1.0 + k) * s
    rl = (+1.0 - k) * s
    rr = (-1.0 + k) * s
    _spam(fl, fr, rl, rr, t)

def drift_right(seconds: float = None, speed: float = None, turn_blend: float = None):
    """
    Drift right in an arc.
    """
    # Classroom-friendly shorthand:
    # drift_right(seconds, 0.55) -> treat 2nd positional as turn_blend.
    if turn_blend is None and speed is not None and -1.0 <= float(speed) <= 1.0:
        turn_blend = float(speed)
        speed = None

    s = float(BASE_SPEED if speed is None else speed)
    t = float(_DRIFT_SECONDS_DEFAULT if seconds is None else seconds)
    k = float(_DRIFT_TURN_BLEND if turn_blend is None else turn_blend)
    k = _clamp(k, 0.0, 1.0)

    # strafe right:  FL+, FR-, RL-, RR+
    # turn right:    FL+, FR-, RL+, RR-
    fl = (+1.0 + k) * s
    fr = (-1.0 - k) * s
    rl = (-1.0 + k) * s
    rr = (+1.0 - k) * s
    _spam(fl, fr, rl, rr, t)

def drift_demo(cycles: int = 2, per_side_seconds: float = 1.2, speed: float = None):
    for _ in range(int(cycles)):
        drift_left(per_side_seconds, speed=speed)
        time.sleep(0.15)
        drift_right(per_side_seconds, speed=speed)
        time.sleep(0.15)

# --------------------------- set_velocity (polar mecanum) ----------------------
def set_velocity(
    speed: float,
    direction_deg: float = 90.0,
    angular_rate: float = 0.0,
    seconds: float = 0.05,
    speed_override: Optional[float] = None,
) -> None:
    """
    Polar-coordinate mecanum drive — mirrors the Hiwonder SDK API.

    Args:
        speed:         Motor speed units (same scale as base_speed / other moves).
        direction_deg: Direction of travel in degrees.
                       90 = forward, 270 = backward, 0 = strafe right, 180 = strafe left.
        angular_rate:  Yaw rotation added on top of translation.
                       Positive → yaw right (clockwise), negative → yaw left.
                       Normalised to ±1; typical line-following range ±0.8.
        seconds:       Duration to hold this velocity.
        speed_override: If given, overrides the speed parameter.

    Mecanum wheel mix (matching Hiwonder mecanum.py sign convention):
        vx  = speed * cos(direction_deg)   — lateral  component
        vy  = speed * sin(direction_deg)   — forward  component
        vp  = −angular_rate * speed        — rotation component (scaled by speed)
        FL = vy + vx − vp
        FR = vy − vx + vp
        RL = vy − vx − vp
        RR = vy + vx + vp
    Then _spam applies the per-wheel SIGN correction for hardware polarity.
    """
    import math

    s = float(speed_override if speed_override is not None else speed)
    rad = math.radians(float(direction_deg))
    vx = math.cos(rad)        # lateral  (−1..1)
    vy = math.sin(rad)        # forward  (−1..1)
    vp = -float(angular_rate) # rotation sign: positive ar → negative vp → yaw right

    fl = (vy + vx - vp) * s
    fr = (vy - vx + vp) * s
    rl = (vy - vx - vp) * s
    rr = (vy + vx + vp) * s
    _spam(fl, fr, rl, rr, float(seconds))


# ------------------------------- drive_for helper ------------------------------
def drive_for(vx: float, vy: float, seconds: float, speed: float = None):
    """
    vx: forward/back   (-1..1)
    vy: left/right     (-1..1)  (positive = right)
    Direct mecanum mix in your motor speed space (no rotation here).
    """
    s = float(BASE_SPEED if speed is None else speed)
    vx = _clamp(float(vx), -1.0, 1.0)
    vy = _clamp(float(vy), -1.0, 1.0)

    # forward: all +
    # right strafe: FL+, FR-, RL-, RR+
    fl = (vx + vy) * s
    fr = (vx - vy) * s
    rl = (vx - vy) * s
    rr = (vx + vy) * s
    _spam(fl, fr, rl, rr, float(seconds))

# ------------------------------------ Horn ------------------------------------
HORN_FILE = os.environ.get("HORN_FILE", "meepmeep.mp3")
HORN_CMD = os.environ.get("HORN_CMD", "mpg123")
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


_SEARCH_DIRS = [
    _safe_cwd_path(),
    Path(__file__).resolve().parent,                 # common/lib
    Path(__file__).resolve().parent.parent / "sounds",  # common/sounds ✅
    Path("/opt/sounds"),
    Path.home() / "Music",
    Path.home() / "Downloads",
]

def _find_horn() -> Optional[Path]:
    p = Path(HORN_FILE).expanduser()
    if p.is_file():
        return p
    for d in _SEARCH_DIRS:
        q = d / HORN_FILE
        if q.is_file():
            return q
    return None

def _mpg123_scale_from_percent(pct: int) -> int:
    try:
        p = int(pct)
    except Exception:
        p = HORN_DEFAULT_VOLUME
    p = max(0, min(100, p))
    return max(1, int(round(32768 * (p / 100.0))))

def horn(path: Optional[str] = None, device: Optional[str] = HORN_DEVICE,
         volume: Optional[int] = None, block: bool = True) -> bool:
    mp3 = Path(path).expanduser() if path else _find_horn()
    if not mp3 or not mp3.exists():
        print("[horn] can't find", HORN_FILE, "-- set HORN_FILE or pass a path")
        return False

    vol_pct = HORN_DEFAULT_VOLUME if volume is None else int(volume)
    scale = _mpg123_scale_from_percent(vol_pct)

    cmd = [HORN_CMD, "-q", "-f", str(scale)]
    if device:
        cmd += ["-a", device]
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

def Horn():
    return horn()

# ------------------------------ Notebook-friendly class ------------------------------
class RobotMoves:
    """
    Notebook-friendly wrapper.
    Signature matches what you were trying to call: RobotMoves(base_speed=..., rate_hz=...)
    """
    def __init__(self, base_speed: float = None, rate_hz: float = None):
        if base_speed is not None:
            set_base_speed(base_speed)
        if rate_hz is not None:
            set_rate(rate_hz)
        enable_motors(True)

    def stop(self): stop()
    def emergency_stop(self): emergency_stop()

    def forward(self, seconds: float = 0.5, speed: float = None): forward(seconds, speed)
    def backward(self, seconds: float = 0.5, speed: float = None): backward(seconds, speed)
    def left(self, seconds: float = 0.5, speed: float = None): left(seconds, speed)
    def right(self, seconds: float = 0.5, speed: float = None): right(seconds, speed)
    def turn_left(self, seconds: float = 0.5, speed: float = None): turn_left(seconds, speed)
    def turn_right(self, seconds: float = 0.5, speed: float = None): turn_right(seconds, speed)
    def diagonal_left(self, seconds: float = 0.8, speed: float = None): diagonal_left(seconds, speed)
    def diagonal_right(self, seconds: float = 0.8, speed: float = None): diagonal_right(seconds, speed)

    def drift_left(self, seconds: float = None, speed: float = None, turn_blend: float = None):
        drift_left(seconds=seconds, speed=speed, turn_blend=turn_blend)

    def drift_right(self, seconds: float = None, speed: float = None, turn_blend: float = None):
        drift_right(seconds=seconds, speed=speed, turn_blend=turn_blend)

    def drive_for(self, vx: float, vy: float, seconds: float, speed: float = None):
        drive_for(vx=vx, vy=vy, seconds=seconds, speed=speed)

    def set_velocity(
        self,
        speed: float,
        direction_deg: float = 90.0,
        angular_rate: float = 0.0,
        seconds: float = 0.05,
    ):
        set_velocity(speed=speed, direction_deg=direction_deg, angular_rate=angular_rate, seconds=seconds)

    def horn(self, *a, **k):
        return horn(*a, **k)
