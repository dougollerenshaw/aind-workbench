"""Every module under scheduler_app must import cleanly.

Why this exists: on 2026-08-10 an edit in progress left `read_api.py`
referencing a `SubjectLookupOut` response model that was never defined. The
tool launcher imports `scheduler_app` to mount this project, so the NameError
raised at import time killed the launcher process — taking query_tool,
fiber_schematic_viewer, upgrader and iacuc_lookup down with it. Four unrelated
production tools were offline because of one unimportable file here.

The hard rule that followed: never leave the working tree unimportable. This
test makes a missing symbol or bad import fail in pytest instead of in Doug's
browser, and it is deliberately fast and dependency-free so there is no excuse
to skip it.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scheduler_app

PACKAGE_DIR = Path(scheduler_app.__file__).resolve().parent

MODULE_NAMES = sorted(
    f"scheduler_app.{info.name}"
    for info in pkgutil.iter_modules([str(PACKAGE_DIR)])
)


def test_package_has_modules_to_check():
    """Guard against the walk silently finding nothing."""
    assert MODULE_NAMES, f"no modules discovered under {PACKAGE_DIR}"
    # The ones the launcher's mount depends on, spelled out so a rename is loud.
    for required in ("scheduler_app.main", "scheduler_app.db", "scheduler_app.read_api",
                     "scheduler_app.admin_api", "scheduler_app.store",
                     "scheduler_app.queries", "scheduler_app.schemas"):
        assert required in MODULE_NAMES, f"{required} missing from {MODULE_NAMES}"


@pytest.mark.parametrize("module_name", MODULE_NAMES)
def test_module_imports(module_name):
    """Importing must not raise — this is what the launcher does at mount time."""
    importlib.import_module(module_name)


def test_launcher_entry_point_imports():
    """The exact import the tool launcher performs to mount this project."""
    from scheduler_app.main import create_app

    assert callable(create_app)


def test_app_module_and_scripts_import():
    """The standalone CLI entry point and the scripts, for the same reason."""
    for module_name in ("app", "scripts.seed", "scripts.export_parquet"):
        importlib.import_module(module_name)
