#!/usr/bin/env python3
"""
Notebook bootstrap helper for lesson folders.
Use in a notebook cell:
    from lesson_loader import setup
    setup()  # bootstraps + preloads common libs
"""

from pathlib import Path
import importlib
import importlib.util
import os
import re
import sys
from typing import Dict, Optional

COMMON_MODULES = [
    "robot_moves",
    "student_robot_moves",
    "eyes_lib",
    "camera_lib",
    "vision_lib",
    "tts_lib",
    "student_animation_lib",
    "student_robot_v2",
    "sound",
    "line_sensors",
    "robot_controller_api",
    "infrared_lib",
    "line_follower_lib",
    "buzzer_lib",
    "sonar_lib",
    "ultrasonic_lib",
    "avoidance_lib",
    "tracking_lib",
    "qrcode_lib",
]

BACKEND_MODULES = [
    "robot_moves",
    "eyes_lib",
    "camera_lib",
    "robot_controller_api",
    "tts_lib",
    "buzzer_lib",
]


def _safe_start_dir() -> Path:
    try:
        return Path.cwd().resolve()
    except Exception:
        home = os.environ.get("HOME")
        if home and Path(home).is_dir():
            return Path(home).resolve()
        return Path("/tmp").resolve()


def _find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(30):
        if (p / "lessons").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    raise FileNotFoundError(f"Could not find lessons root from {start}")


def _detect_workspace_login_warning(start: Path) -> Optional[str]:
    start_str = str(start)

    if not start_str.startswith("/opt/robot/"):
        return None
    if "/students/workspaces/" in start_str:
        return None

    return (
        "Jupyter does not appear to be running from a student workspace. "
        "Please log in to the student Jupyter workspace and reopen the lesson notebook there. "
        f"Current path: {start}"
    )


def _resolve_common_lib(root: Path) -> Path:
    candidates = []
    for env_name in ("MATA_COMMON_LIB_DIR", "LESSON_CACHE_COMMON_LIB_DIR"):
        value = str(os.environ.get(env_name, "")).strip()
        if value:
            candidates.append(Path(value).expanduser())

    candidates.extend([
        Path("/opt/robot/students/lessons_cache/common/lib"),
        Path("/opt/robot/students/lesson_cache/common/lib"),
        root / "common" / "lib",
    ])

    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_dir():
            return candidate

    preferred = candidates[0] if candidates else (root / "common" / "lib")
    raise FileNotFoundError(
        "Could not find common/lib. Checked: " + ", ".join(str(p) for p in candidates)
    )


def _parse_domain_from_name(name: str) -> Optional[str]:
    m = re.search(r"(\d+)$", str(name).strip())
    if not m:
        return None
    return str(int(m.group(1)))


def _resolve_domain(default_domain: Optional[object]) -> str:
    if default_domain is not None:
        return str(default_domain)

    for k in ("ROS_DOMAIN_ID", "ROBOT_DOMAIN_ID", "ROBOT_NUMBER"):
        v = os.environ.get(k)
        if v and str(v).strip().isdigit():
            return str(int(str(v).strip()))

    for k in ("ROBOT_NAME", "ROBOT_ID", "HOSTNAME"):
        v = os.environ.get(k)
        if v:
            parsed = _parse_domain_from_name(v)
            if parsed is not None:
                return parsed

    return "0"


def _resolve_backend(backend: Optional[str]) -> str:
    if backend is not None:
        b = str(backend).strip().lower()
        if b in ("sim", "simulator"):
            return "sim"
        if b in ("real", "robot", "hardware"):
            return "real"
        if b not in ("", "auto", "default"):
            raise ValueError(f"Unknown backend={backend!r}. Use 'sim' or 'real'.")

    if str(os.environ.get("MATA_BACKEND", "")).strip().lower() == "sim":
        return "sim"
    if str(os.environ.get("MATA_SIM", "")).strip() == "1":
        return "sim"
    return "real"


def _apply_backend_env(selected: str) -> None:
    if selected == "sim":
        os.environ["MATA_BACKEND"] = "SIM"
        os.environ["MATA_SIM"] = "1"
    else:
        os.environ["MATA_BACKEND"] = "REAL"
        os.environ.pop("MATA_SIM", None)


def _purge_backend_modules() -> None:
    for name in BACKEND_MODULES:
        sys.modules.pop(name, None)


def _expose_modules(mods: Dict[str, object]) -> None:
    try:
        frame = sys._getframe(2)
        g = frame.f_globals
    except Exception:
        return

    g.update(mods)
    if "robot_moves" in mods:
        g.setdefault("rm", mods["robot_moves"])


def setup(
    default_domain: Optional[object] = None,
    backend: Optional[str] = None,
    verbose: bool = True,
    preload_common: bool = True,
    expose_globals: bool = True,
):
    """
    Configure sys.path for common/lib + lessons/lib, run bootstrap,
    and optionally preload common lesson modules.

    default_domain:
      - None: infer from env (ROS_DOMAIN_ID / robot vars), fallback "0"
      - int/str: explicit domain override
    backend:
      - "sim": use simulator modules
      - "real": use hardware modules
      - None: use env/default (REAL)
    """
    selected_backend = _resolve_backend(backend)
    previous_backend = str(os.environ.get("MATA_ACTIVE_BACKEND", "")).strip().lower()
    _apply_backend_env(selected_backend)
    if previous_backend != selected_backend:
        _purge_backend_modules()
    os.environ["MATA_ACTIVE_BACKEND"] = selected_backend
    if verbose:
        print(f"[lesson_loader] backend={selected_backend.upper()}")

    start = _safe_start_dir()

    try:
        os.chdir(str(start))
    except Exception:
        pass

    login_warning = _detect_workspace_login_warning(start)

    try:
        root = _find_repo_root(start)
    except FileNotFoundError as e:
        if login_warning:
            raise FileNotFoundError(f"{e}\n{login_warning}") from e
        raise
    common_lib = _resolve_common_lib(root)
    lessons_lib = root / "lessons" / "lib"

    for path in (common_lib, lessons_lib):
        s = str(path)
        if path.exists() and s not in sys.path:
            sys.path.insert(0, s)

    if login_warning:
        print(f"[lesson_loader] WARNING: {login_warning}")

    if verbose:
        print(f"[lesson_loader] common_lib={common_lib}")
        print(f"[lesson_loader] lessons_lib={lessons_lib}")

    bootstrap_path = common_lib / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("lesson_bootstrap", str(bootstrap_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load bootstrap from {bootstrap_path}")
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)

    domain = _resolve_domain(default_domain)
    os.environ["ROS_DOMAIN_ID"] = domain

    if hasattr(bootstrap, "init"):
        info = bootstrap.init(default_domain=domain, verbose=verbose)
    elif hasattr(bootstrap, "bootstrap"):
        info = bootstrap.bootstrap(default_domain=domain, verbose=verbose)
    else:
        raise AttributeError(
            f"bootstrap module missing both init() and bootstrap(): {bootstrap_path}"
        )

    loaded: Dict[str, object] = {}
    if preload_common:
        for name in COMMON_MODULES:
            try:
                loaded[name] = importlib.import_module(name)
            except Exception as e:
                if verbose:
                    print(f"[lesson_loader] skip {name}: {e}")

        if expose_globals and loaded:
            _expose_modules(loaded)

        if verbose and loaded:
            print("Preloaded:", ", ".join(sorted(loaded.keys())))

    return {
        "bootstrap": info,
        "modules": loaded,
        "ros_domain_id": domain,
        "backend": selected_backend,
    }
