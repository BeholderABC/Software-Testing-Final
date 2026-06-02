"""
run_context.py  --  Per-run output directory management.

Every pipeline session — one visit that begins on the Step 0 landing
page — owns a single timestamped directory under ``outputs/``::

    outputs/run_<YYYYMMDD_HHMMSS>/
        docs/    auto-generated Markdown reports (risk analysis, test
                 plan, detailed test design & execution)
        data/    exported CSV / JSON / Excel artefacts

The run id is fixed when the session starts (see ``_init_state`` in
``app.py``); every artefact produced during that session is written
beneath the same directory, so a run is self-contained and reproducible.

Naming uses a wall-clock timestamp rather than an incrementing counter
so that no shared counter file has to be persisted, parallel sessions
never collide, and a fresh checkout starts cleanly.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Optional

# Root that holds every run directory. Kept in version control via its
# ``.gitkeep``; the run directories themselves are git-ignored
# (see ``.gitignore``: ``outputs/*`` with ``!outputs/.gitkeep``).
OUTPUTS_ROOT = "outputs"


def new_run_id(now: Optional[datetime] = None) -> str:
    """Return a fresh run id of the form ``run_YYYYMMDD_HHMMSS``."""
    return (now or datetime.now()).strftime("run_%Y%m%d_%H%M%S")


def run_dir(run_id: str, root: str = OUTPUTS_ROOT) -> str:
    """Absolute-or-relative path of a run's top-level directory."""
    return os.path.join(root, run_id)


def docs_dir(run_id: str, root: str = OUTPUTS_ROOT) -> str:
    """Path of the run's ``docs/`` sub-directory (generated Markdown)."""
    return os.path.join(run_dir(run_id, root), "docs")


def data_dir(run_id: str, root: str = OUTPUTS_ROOT) -> str:
    """Path of the run's ``data/`` sub-directory (exported artefacts)."""
    return os.path.join(run_dir(run_id, root), "data")


def runs_dir(run_id: str, root: str = OUTPUTS_ROOT) -> str:
    """Path of the run's ``runs/`` sub-directory.

    Holds the transient ``_streamlit_run_*.json`` test-case payloads that
    each Step 8 execution hands to the pytest subprocess. Grouping them
    under the run keeps the ``outputs/`` root clean.
    """
    return os.path.join(run_dir(run_id, root), "runs")


def ensure_run_dirs(run_id: str, root: str = OUTPUTS_ROOT) -> Dict[str, str]:
    """Create the run directory tree if absent and return its paths.

    Returns a dict with keys ``root``, ``docs``, ``data`` and ``runs``.
    Safe to call repeatedly: directories are created with ``exist_ok=True``
    so re-entering a step never raises.
    """
    paths = {
        "root": run_dir(run_id, root),
        "docs": docs_dir(run_id, root),
        "data": data_dir(run_id, root),
        "runs": runs_dir(run_id, root),
    }
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    return paths
