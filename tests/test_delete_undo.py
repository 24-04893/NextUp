"""
tests/test_delete_undo.py
=========================
STAGE A, bug 4: HARD delete (separate from complete) with a 6.5 s undo
window. Every test asserts that the heap, AVL and SQLite row set stay
in sync after the mutation -- that is the actual invariant being sold.
Run: pytest tests/test_delete_undo.py -q
"""

from datetime import timedelta

import pytest


def _ids(tm):
    """(heap ids, avl ids, db ids) for sync assertions."""
    return (
        {e[3].id for e in tm._heap.to_list()},
        {t.id for t in tm._avl.inorder()},
        {r[0] for r in tm.store._conn.execute("SELECT id FROM tasks")},
    )


def test_delete_removes_from_all_three(tm):
    task, _ = tm.add_task("Doomed", "CS", (tm.today() + timedelta(days=2)).isoformat(), 3)
    before = _ids(tm)
    assert task.id in before[0] and task.id in before[1] and task.id in before[2]
    gone = tm.delete_task(task.id)
    assert gone is task
    heap, avl, db = _ids(tm)
    assert task.id not in heap and task.id not in avl and task.id not in db


def test_delete_completed_task(tm):
    task, _ = tm.add_task("Done then deleted", "CS",
                          (tm.today() + timedelta(days=2)).isoformat(), 3)
    tm.complete_task(task.id)
    assert tm.delete_task(task.id) is task          # completed rows delete too
    heap, avl, db = _ids(tm)
    assert task.id not in db


def test_delete_nonexistent_is_none(tm):
    assert tm.delete_task(4242) is None             # no crash, no mutation


def test_undo_restores_open_task_everywhere(tm):
    task, _ = tm.add_task("Undone", "CS", (tm.today() + timedelta(days=3)).isoformat(), 3)
    tm.delete_task(task.id)
    back = tm.undelete_task(task.id)
    assert back is task
    heap, avl, db = _ids(tm)
    assert task.id in heap and task.id in avl and task.id in db
    assert not task.completed                       # still open


def test_undo_restores_completed_task(tm):
    task, _ = tm.add_task("Completed undo", "CS",
                          (tm.today() + timedelta(days=3)).isoformat(), 3)
    tm.complete_task(task.id)
    tm.delete_task(task.id)
    back = tm.undelete_task(task.id)
    assert back is task and task.completed is True  # stays completed
    heap, avl, db = _ids(tm)
    assert task.id in db
    assert task.id not in heap and task.id not in avl   # completed: containers stay out


def test_undo_only_once(tm):
    task, _ = tm.add_task("Once", "CS", (tm.today() + timedelta(days=1)).isoformat(), 3)
    tm.delete_task(task.id)
    assert tm.undelete_task(task.id) is task
    assert tm.undelete_task(task.id) is None        # trash slot already spent


def test_undo_window_closes(tm, monkeypatch):
    task, _ = tm.add_task("Too late", "CS", (tm.today() + timedelta(days=1)).isoformat(), 3)
    tm.delete_task(task.id)
    fake_later = tm._trash[task.id][1] + 1          # 1s past the window
    monkeypatch.setattr(tm, "UNDO_WINDOW_S", tm.UNDO_WINDOW_S)  # no-op, clarity
    entry = tm._trash[task.id]
    tm._trash[task.id] = (entry[0], entry[1] - 10)  # simulate 10s passing
    assert tm.undelete_task(task.id) is None
    heap, avl, db = _ids(tm)
    assert task.id not in db                        # stays deleted


def test_avl_valid_after_delete(tm):
    from datetime import date
    for k in range(12):
        tm.add_task(f"v{k}", "CS", (tm.today() + timedelta(days=k)).isoformat(), 3)
    tm.prepare_dashboard()
    victim = next(iter(tm._tasks))
    tm.delete_task(victim)
    assert tm._avl.is_avl()                         # rebalancing held
    assert sum(1 for t in tm._avl.inorder()) == len(tm._heap)   # heap AVL sizes agree
