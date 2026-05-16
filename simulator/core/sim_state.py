"""Shared state store for simulator GUI and lesson shim modules."""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_ENV = "MATA_SIM_STATE"
DEFAULT_STATE_FILE = "/tmp/mataturbopi_sim_state.json"
DEFAULT_LESSON_ENV = "MATA_SIM_LESSON"
DEFAULT_LEVEL_ENV = "MATA_SIM_LEVEL"
ROBOT_RADIUS_M = 0.11
SONAR_MAX_RANGE_M = 2.0
SONAR_HALF_WIDTH_M = 0.08

_LESSON_ALIASES = {
    "lesson11": "lesson01",
    "lesson12": "lesson02",
    "lesson13": "lesson03",
    "lesson14": "lesson04",
    "lesson15": "lesson05",
    "lesson16": "lesson06",
    "lesson17": "lesson07",
}


def state_path() -> Path:
    return Path(os.environ.get(STATE_ENV, DEFAULT_STATE_FILE)).expanduser().resolve()


def _default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": time.time(),
        "lesson": {
            "id": None,
            "level": None,
            "course_id": "default",
        },
        "robot": {
            "x": 0.0,
            "y": 0.0,
            "heading_deg": 0.0,
            "vx": 0.0,
            "vy": 0.0,
            "omega_deg_s": 0.0,
        },
        "eyes": {
            "left": [0, 0, 0],
            "right": [0, 0, 0],
        },
        "camera": {
            "yaw": 1500,
            "pitch": 1500,
            "center": 1500,
            "min_pos": 1000,
            "max_pos": 2000,
        },
        "sonar": {
            "distance_m": None,
            "distance_cm": None,
            "distance_mm": None,
            "max_range_m": SONAR_MAX_RANGE_M,
        },
        "collision": {
            "active": False,
            "message": "",
            "obstacle_id": None,
        },
        # Infrared line sensor state — 4 boolean channels [s0, s1, s2, s3] (left→right).
        # The simulator does not auto-compute IR from robot position; set manually for
        # testing specific patterns, or leave as all-False (no line detected).
        "infrared": {
            "sensors": [False, False, False, False],
        },
        "course": {
            "id": "default",
            "title": "Default Empty Course",
            "obstacles": [],
            "people": [],
        },
        "trace": [],
        "last_command": "",
    }


def _courses_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "courses"


def _course_file_for(lesson_id: Optional[str], level_id: Optional[str]) -> Path:
    if lesson_id and level_id:
        candidate = _courses_dir() / f"{lesson_id}_{level_id}.json"
        if candidate.exists():
            return candidate
        mapped = _LESSON_ALIASES.get(str(lesson_id))
        if mapped:
            alias_candidate = _courses_dir() / f"{mapped}_{level_id}.json"
            if alias_candidate.exists():
                return alias_candidate
    return _courses_dir() / "default.json"


def _load_course_config(lesson_id: Optional[str], level_id: Optional[str]) -> Dict[str, Any]:
    path = _course_file_for(lesson_id, level_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"id": "default", "title": "Default Empty Course", "robot_start": {}, "obstacles": [], "people": []}
    data.setdefault("id", "default")
    data.setdefault("title", data["id"])
    data.setdefault("robot_start", {})
    data.setdefault("obstacles", [])
    data.setdefault("people", [])
    return data


def _state_lesson_from_env() -> tuple[Optional[str], Optional[str]]:
    lesson = os.environ.get(DEFAULT_LESSON_ENV)
    level = os.environ.get(DEFAULT_LEVEL_ENV)
    return (lesson.strip() if lesson else None, level.strip() if level else None)


def _refresh_course(state: Dict[str, Any]) -> Dict[str, Any]:
    lesson = state.get("lesson", {}) if isinstance(state.get("lesson"), dict) else {}
    lesson_id = lesson.get("id")
    level_id = lesson.get("level")
    env_lesson, env_level = _state_lesson_from_env()
    if env_lesson:
        lesson_id = env_lesson
    if env_level:
        level_id = env_level
    course = _load_course_config(lesson_id, level_id)
    state["lesson"] = {
        "id": lesson_id,
        "level": level_id,
        "course_id": course.get("id", "default"),
    }
    state["course"] = {
        "id": course.get("id", "default"),
        "title": course.get("title", course.get("id", "default")),
        "obstacles": list(course.get("obstacles", [])),
        "people": list(course.get("people", [])),
    }
    start = course.get("robot_start", {}) if isinstance(course.get("robot_start"), dict) else {}
    robot = state.get("robot", {})
    if not state.get("trace"):
        robot["x"] = float(start.get("x", robot.get("x", 0.0)))
        robot["y"] = float(start.get("y", robot.get("y", 0.0)))
        robot["heading_deg"] = float(start.get("heading_deg", robot.get("heading_deg", 0.0)))
    return state


def _compute_collision(state: Dict[str, Any]) -> Dict[str, Any]:
    robot = state["robot"]
    rx = float(robot.get("x", 0.0))
    ry = float(robot.get("y", 0.0))
    collided = None
    for obs in state.get("course", {}).get("obstacles", []):
        ox = float(obs.get("x", 0.0))
        oy = float(obs.get("y", 0.0))
        rr = float(obs.get("radius_m", 0.04)) + ROBOT_RADIUS_M
        if math.hypot(ox - rx, oy - ry) <= rr:
            collided = obs
            break
    if collided is None:
        state["collision"] = {"active": False, "message": "", "obstacle_id": None}
    else:
        state["collision"] = {
            "active": True,
            "message": "Collision",
            "obstacle_id": collided.get("id"),
        }
        robot["vx"] = 0.0
        robot["vy"] = 0.0
        robot["omega_deg_s"] = 0.0
        state["last_command"] = "Collision"
    return state


def _compute_sonar(state: Dict[str, Any]) -> Dict[str, Any]:
    robot = state["robot"]
    rx = float(robot.get("x", 0.0))
    ry = float(robot.get("y", 0.0))
    heading = math.radians(float(robot.get("heading_deg", 0.0)))
    forward_x = -math.sin(heading)
    forward_y = math.cos(heading)
    closest: Optional[float] = None
    for obs in state.get("course", {}).get("obstacles", []):
        ox = float(obs.get("x", 0.0))
        oy = float(obs.get("y", 0.0))
        radius = float(obs.get("radius_m", 0.04))
        dx = ox - rx
        dy = oy - ry
        forward_dist = dx * forward_x + dy * forward_y
        if forward_dist <= 0.0 or forward_dist > SONAR_MAX_RANGE_M:
            continue
        lateral = abs(dx * forward_y - dy * forward_x)
        if lateral > (SONAR_HALF_WIDTH_M + radius):
            continue
        edge_dist = max(0.0, forward_dist - radius)
        if closest is None or edge_dist < closest:
            closest = edge_dist
    if closest is None:
        state["sonar"] = {
            "distance_m": None,
            "distance_cm": None,
            "distance_mm": None,
            "max_range_m": SONAR_MAX_RANGE_M,
        }
    else:
        state["sonar"] = {
            "distance_m": round(float(closest), 3),
            "distance_cm": round(float(closest) * 100.0, 1),
            "distance_mm": int(round(float(closest) * 1000.0)),
            "max_range_m": SONAR_MAX_RANGE_M,
        }
    return state


def _recompute_environment(state: Dict[str, Any]) -> Dict[str, Any]:
    _refresh_course(state)
    _compute_collision(state)
    _compute_sonar(state)
    return state


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="sim_state_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_state() -> Dict[str, Any]:
    path = state_path()
    if not path.exists():
        st = _default_state()
        _atomic_write_json(path, st)
        return st

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _default_state()
        _atomic_write_json(path, data)

    merged = _default_state()
    merged.update({k: v for k, v in data.items() if k in merged and not isinstance(merged[k], dict)})
    for key in ("robot", "eyes", "camera"):
        if isinstance(data.get(key), dict):
            merged[key].update(data[key])
    for key in ("lesson", "sonar", "collision", "course", "infrared"):
        if isinstance(data.get(key), dict):
            merged[key].update(data[key])
    if isinstance(data.get("trace"), list):
        merged["trace"] = data["trace"]
    if isinstance(data.get("last_command"), str):
        merged["last_command"] = data["last_command"]
    merged["updated_at"] = float(data.get("updated_at", merged["updated_at"]))
    _recompute_environment(merged)
    return merged


def save_state(state: Dict[str, Any]) -> Dict[str, Any]:
    _recompute_environment(state)
    state["updated_at"] = time.time()
    _atomic_write_json(state_path(), state)
    return state


def reset_state() -> Dict[str, Any]:
    prev = None
    try:
        prev = load_state()
    except Exception:
        prev = None
    st = _default_state()
    if isinstance(prev, dict) and isinstance(prev.get("lesson"), dict):
        st["lesson"].update(prev["lesson"])
    _recompute_environment(st)
    save_state(st)
    return st


def set_active_lesson(lesson_id: Optional[str], level_id: Optional[str]) -> Dict[str, Any]:
    st = load_state()
    st["lesson"] = {
        "id": lesson_id,
        "level": level_id,
        "course_id": st.get("lesson", {}).get("course_id", "default"),
    }
    st["trace"] = []
    _refresh_course(st)
    course = _load_course_config(lesson_id, level_id)
    start = course.get("robot_start", {}) if isinstance(course.get("robot_start"), dict) else {}
    st["robot"]["x"] = float(start.get("x", 0.0))
    st["robot"]["y"] = float(start.get("y", 0.0))
    st["robot"]["heading_deg"] = float(start.get("heading_deg", 0.0))
    st["robot"]["vx"] = 0.0
    st["robot"]["vy"] = 0.0
    st["robot"]["omega_deg_s"] = 0.0
    st["last_command"] = f"load_course:{lesson_id or 'default'}:{level_id or 'default'}"
    return save_state(st)


def append_trace(state: Dict[str, Any], label: str) -> None:
    r = state["robot"]
    item = {
        "x": float(r["x"]),
        "y": float(r["y"]),
        "heading_deg": float(r["heading_deg"]),
        "t": time.time(),
        "label": label,
    }
    trace: List[Dict[str, Any]] = state.setdefault("trace", [])
    trace.append(item)
    if len(trace) > 600:
        del trace[:-600]


def apply_robot_motion(
    state: Dict[str, Any],
    vx_m_s: float,
    vy_m_s: float,
    omega_deg_s: float,
    seconds: float,
    label: str,
) -> Dict[str, Any]:
    dt = max(0.0, float(seconds))
    r = state["robot"]

    heading = math.radians(float(r["heading_deg"]))
    c = math.cos(heading)
    s = math.sin(heading)

    # Simulator convention:
    # - vx = forward/back
    # - vy = right/left (positive = right)
    # - heading_deg = 0 means facing up on screen (+Y)
    #
    # Render math uses local X=right and local Y=forward,
    # so map (vy, vx) into (local_x, local_y) before rotating.
    wx = float(vy_m_s) * c - float(vx_m_s) * s
    wy = float(vy_m_s) * s + float(vx_m_s) * c

    r["x"] = float(r["x"]) + wx * dt
    r["y"] = float(r["y"]) + wy * dt
    r["heading_deg"] = (float(r["heading_deg"]) + float(omega_deg_s) * dt) % 360.0
    r["vx"] = float(vx_m_s)
    r["vy"] = float(vy_m_s)
    r["omega_deg_s"] = float(omega_deg_s)

    state["last_command"] = str(label)
    append_trace(state, label)
    _compute_collision(state)
    _compute_sonar(state)
    return state
