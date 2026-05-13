#!/usr/bin/env python3
"""Compatibility shim for student_robot_v2.

The V2 implementation now lives in common/lib so all lessons and robot
workspaces resolve the same shared version.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _raise_workspace_import_error(path: Path, detail: Exception | str) -> None:
    message = str(detail).strip()
    lower = message.lower()
    if "permission denied" in lower or "operation not permitted" in lower or "errno 13" in lower:
        raise ImportError(
            "Student workspace access required. "
            "This notebook cannot read the shared V2 robot library. "
            "Please log in to the student Jupyter workspace again and reopen the notebook.\n"
            f"Library path: {path}\n"
            f"Technical detail: {message}"
        ) from None
    raise ImportError(message) from None


_COMMON_IMPL = Path(__file__).resolve().parents[2] / "common" / "lib" / "student_robot_v2.py"
_SPEC = importlib.util.spec_from_file_location("_student_robot_v2_common", _COMMON_IMPL)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load common V2 library from {_COMMON_IMPL}")
_MODULE = importlib.util.module_from_spec(_SPEC)
try:
    _SPEC.loader.exec_module(_MODULE)
except Exception as e:
    _raise_workspace_import_error(_COMMON_IMPL, e)

__all__ = getattr(
    _MODULE,
    "__all__",
    [name for name in dir(_MODULE) if not name.startswith("_") or name == "__version__"],
)

for _name in __all__:
    globals()[_name] = getattr(_MODULE, _name)
