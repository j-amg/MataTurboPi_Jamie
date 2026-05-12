# demo_bootstrap.py
# Keeps notebooks clean: fixes broken cwd, finds repo root, adds sys.path,
# and cleans up ROS env (bad CycloneDDS URI).

from pathlib import Path
import os
import sys

__version__ = "1.6"

BROKEN_CYCLONE_URI = "file:///etc/cyclonedds/config.xml"

def safe_start_dir() -> Path:
    try:
        return Path.cwd().resolve()
    except FileNotFoundError:
        home = os.environ.get("HOME")
        if home:
            return Path(home).resolve()
        return Path("/tmp").resolve()

def find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(25):
        if (p / "lessons").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    raise FileNotFoundError(f"Could not find repo root from start={start}")


def _existing_lessons_lib() -> Path | None:
    for entry in sys.path:
        try:
            path = Path(entry)
        except Exception:
            continue
        if path.name == "lib" and path.parent.name == "lessons" and path.exists():
            return path
    return None


_SESSION_CANDIDATES = [
    Path(os.environ.get("STUDENT_SESSION_PATH", "/opt/robot/lessons/state/student_session.json")),
    Path("/opt/robot/lessons/state/student_session.json"),
    Path("/opt/robot/students/state/student_session.json"),
]


def _student_session_exists() -> bool:
    seen = set()
    for p in _SESSION_CANDIDATES:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        try:
            if p.exists():
                return True
        except Exception:
            pass
    return False


def _missing_lib_error(lib_path: Path) -> RuntimeError:
    if _student_session_exists():
        msg = (
            "\n"
            "  Robot library files not found — the lesson bundle has not been applied yet.\n"
            "\n"
            "  You are logged in, but your lesson may still be loading.\n"
            "  Please wait a moment then restart the notebook kernel and try again.\n"
            "\n"
            f"  (Expected library at: {lib_path})"
        )
    else:
        msg = (
            "\n"
            "  Robot library files not found — please log in first.\n"
            "\n"
            "  To use this notebook:\n"
            "  1. Open the robot web page (your teacher will give you the address)\n"
            "  2. Enter your name and class code to log in\n"
            "  3. Return to this notebook and restart the kernel\n"
            "\n"
            f"  (Expected library at: {lib_path})"
        )
    return RuntimeError(msg)


def resolve_common_lib(root: Path) -> Path:
    candidates = []
    for env_name in ("MATA_COMMON_LIB_DIR", "LESSON_CACHE_COMMON_LIB_DIR"):
        value = str(os.environ.get(env_name, "")).strip()
        if value:
            candidates.append(Path(value).expanduser())

    candidates.extend([
        Path("/opt/robot/students/lessons_cache/common/lib"),
        root / "common" / "lib",
        Path("/opt/robot/common/lib"),
    ])

    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[-1]


def resolve_lessons_lib(root: Path) -> Path:
    existing = _existing_lessons_lib()
    if existing is not None:
        return existing

    candidates = []
    value = str(os.environ.get("MATA_LESSONS_LIB_DIR", "")).strip()
    if value:
        candidates.append(Path(value).expanduser())

    candidates.extend([
        root / "lessons" / "lib",
        Path("/opt/robot/students/lessons_cache/lessons/lib"),
        Path("/opt/robot/lessons/lib"),
    ])

    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[-1]

def setup_paths() -> dict:
    start = safe_start_dir()
    root = find_repo_root(start)
    common_lib = resolve_common_lib(root)
    lessons_lib = resolve_lessons_lib(root)
    sim_enabled = str(os.environ.get("MATA_BACKEND", "")).strip().lower() == "sim" or os.environ.get("MATA_SIM", "").strip() == "1"
    if not sim_enabled and not common_lib.exists():
        raise _missing_lib_error(common_lib)
    sim_shims = root / "simulator" / "shims"

    sim_shims_s = str(sim_shims)
    sys.path[:] = [p for p in sys.path if p != sim_shims_s]

    ordered_paths = []
    if sim_enabled and sim_shims.is_dir():
        ordered_paths.append(sim_shims)
        ordered_paths.append(root)
    ordered_paths.extend([common_lib, lessons_lib])

    for path in reversed(ordered_paths):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    if sim_enabled:
        try:
            from simulator.core.sim_state import set_active_lesson

            lesson_id = None
            level_id = None
            for part in start.parts:
                if part.startswith("lesson") and len(part) >= 8:
                    lesson_id = part
                if part.startswith("level_"):
                    level_id = part
            set_active_lesson(lesson_id, level_id)
        except Exception:
            pass

    return {
        "START": str(start),
        "ROOT": str(root),
        "COMMON_LIB": str(common_lib),
        "LESSONS_LIB": str(lessons_lib),
        "SIM_ENABLED": sim_enabled,
        "SIM_SHIMS": str(sim_shims),
    }

def setup_ros_env(default_domain: str = "0") -> dict:
    # Remove the known-bad CycloneDDS config
    if os.environ.get("CYCLONEDDS_URI") == BROKEN_CYCLONE_URI:
        os.environ.pop("CYCLONEDDS_URI", None)

    os.environ.setdefault("ROS_DOMAIN_ID", str(default_domain))
    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")

    return {
        "ROS_DOMAIN_ID": os.environ.get("ROS_DOMAIN_ID"),
        "RMW_IMPLEMENTATION": os.environ.get("RMW_IMPLEMENTATION"),
        "CYCLONEDDS_URI": os.environ.get("CYCLONEDDS_URI"),
    }


def setup_camera_fallback() -> dict:
    """
    Let notebooks that call cv2.VideoCapture(0) use the robot_ops vision API
    when direct V4L2 capture is unavailable.
    """
    if str(os.environ.get("MATA_BACKEND", "")).strip().lower() == "sim":
        return {"OPS_WEB_CAMERA_FALLBACK": False}
    try:
        import vision_lib

        installed = bool(vision_lib.install_opencv_capture_fallback())
        return {"OPS_WEB_CAMERA_FALLBACK": installed}
    except Exception as e:
        return {
            "OPS_WEB_CAMERA_FALLBACK": False,
            "OPS_WEB_CAMERA_FALLBACK_ERROR": str(e),
        }


def bootstrap(default_domain: str = "0", verbose: bool = True) -> dict:
    paths = setup_paths()
    env = setup_ros_env(default_domain=default_domain)
    camera = setup_camera_fallback()

    info = {**paths, **env, **camera}
    if verbose:
        print("START:", info["START"])
        print("Repo root:", info["ROOT"])
        print("Using common lib:", info["COMMON_LIB"])
        print("Using lessons lib:", info["LESSONS_LIB"])
        print("MATA_BACKEND =", "SIM" if info.get("SIM_ENABLED") else "REAL")
        if info.get("SIM_ENABLED"):
            print("Simulator shims:", info.get("SIM_SHIMS"))
        print("ROS_DOMAIN_ID =", info["ROS_DOMAIN_ID"])
        print("RMW_IMPLEMENTATION =", info["RMW_IMPLEMENTATION"])
        print("CYCLONEDDS_URI =", info["CYCLONEDDS_URI"])
        print("OPS_WEB_CAMERA_FALLBACK =", info.get("OPS_WEB_CAMERA_FALLBACK"))
    return info
