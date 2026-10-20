"""
conftest.py -- pytest wiring for NextUp.

Two problems to solve here:

1. The application modules live one directory UP (nextup/, not
   nextup/tests/), and are written as flat modules (import task, import
   heap...). pytest's rootdir injection only adds the tests/ folder, so
   we prepend the parent to sys.path ourselves -- exactly like running
   `python app.py` from nextup/ would.

2. Everything must be ISOLATED per test:
   * TaskManager fixtures point at a throwaway SQLite file (tmp_path),
     so tests never read or damage your real nextup.db.
   * Route tests import app.py ONCE; between tests the shared manager
     is wiped on BOTH layers (dict + SQL table) via wipe_manager().

Run from nextup/:  pytest tests/ -q
"""

import sys
from pathlib import Path

# Make `import task`, `import heap`, ... work from inside tests/.
PARENT = str(Path(__file__).resolve().parent.parent)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

import pytest

from task_manager import TaskManager
from heap import MaxHeap
from avl_tree import AVLTree


def _fake_today(tm, year=2026, month=10, day=20):
    """Freeze a manager's idea of 'today' so tests never drift with the
    real calendar. (Binds a method override, the classic Python trick.)"""
    from datetime import date
    fixed = date(year, month, day)
    tm.today = lambda: fixed
    return fixed


@pytest.fixture
def tm(tmp_path, monkeypatch):
    """A fresh TaskManager on a throwaway database, with 'today' pinned
    to 2026-10-20 so scoring math is deterministic. The legacy-JSON env
    var points at a nonexistent file, so no real tasks.json migrates in."""
    monkeypatch.setenv("NEXTUP_LEGACY_JSON", str(tmp_path / "no-legacy.json"))
    manager = TaskManager(str(tmp_path / "unit.db"))
    _fake_today(manager)
    yield manager
    manager.store.close()


# ----------------------------------------------------------------------
# Route tests (they go through the real Flask app)
# ----------------------------------------------------------------------
@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    """The real app module with its global `manager` swapped for a
    throwaway one. Env vars are set BEFORE importing (app.py reads them
    at import time) and restored after, so nothing leaks between tests.
    NEXTUP_LEGACY_JSON points at a nonexistent file: route tests must
    NOT migrate your real tasks.json."""
    monkeypatch.setenv("NEXTUP_DB_FILE", str(tmp_path / "routes.db"))
    monkeypatch.setenv("NEXTUP_LEGACY_JSON", str(tmp_path / "no-legacy.json"))
    import app as app_module          # noqa: E402  (needs sys.path above)
    manager = TaskManager(str(tmp_path / "routes.db"))
    _fake_today(manager)
    old_manager = app_module.manager
    app_module.manager = manager      # routes read the module global
    yield app_module
    manager.store.close()
    app_module.manager = old_manager


@pytest.fixture
def client(app_mod):
    """Just the test_client (tests reach the data through the API views)."""
    with app_mod.app.test_client() as test_client:
        yield test_client
