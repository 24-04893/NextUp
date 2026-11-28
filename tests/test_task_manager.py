"""
tests/test_task_manager.py
==========================
The glue layer: add, edit (with heap + AVL sync), complete (soft
delete + timestamp), restore, nonexistents, empty inputs -- plus
persistence across managers and the one-time JSON migration.
Run: pytest tests/test_task_manager.py -q
"""

import json

import pytest

from datetime import timedelta
from task import Task
from task_manager import TaskManager
from scoring import priority_score

FIXED_TODAY = None   # set per-test by the `tm` fixture via tm.today()

def _due(tm, days):
    """Deadline due `days` days from the manager's pinned 'today'."""
    return (tm.today() + timedelta(days=days)).isoformat()


# ------------------------------------------------------------------
# Validation gates (every field)
# ------------------------------------------------------------------
def test_add_empty_name_rejected(tm):
    with pytest.raises(ValueError, match="empty"):
        tm.add_task("   ", "CS", _due(tm, 3), 3)


def test_add_name_length_capped(tm):
    long_name = "x" * 200
    with pytest.raises(ValueError, match="too long"):
        tm.add_task(long_name, "CS", _due(tm, 3), 3)


def test_add_bad_difficulty_rejected(tm):
    for bad in (0, 6, "abc", ""):
        with pytest.raises(ValueError, match="Difficulty"):
            tm.add_task("Name", "CS", _due(tm, 3), bad)


def test_add_hours_nonpositive_rejected(tm):
    for bad in (0, -2, "nope"):
        with pytest.raises(ValueError, match="hours"):
            tm.add_task("Name", "CS", _due(tm, 3), 3, estimated_hours=bad)


def test_add_hours_over_cap_rejected(tm):
    with pytest.raises(ValueError, match="hours"):
        tm.add_task("Name", "CS", _due(tm, 3), 3, estimated_hours=25)


def test_add_bad_type_rejected(tm):
    with pytest.raises(ValueError, match="type"):
        tm.add_task("Name", "CS", _due(tm, 3), 3, task_type="party")


def test_add_bad_date_rejected(tm):
    with pytest.raises(ValueError, match="valid date"):
        tm.add_task("Name", "CS", "2026-13-99", 3)


def test_add_bad_time_rejected(tm):
    with pytest.raises(ValueError, match="HH:MM"):
        tm.add_task("Name", "CS", _due(tm, 3), 3, deadline_time="25:00")
    with pytest.raises(ValueError, match="HH:MM"):
        tm.add_task("Name", "CS", _due(tm, 3), 3, deadline_time="noon")


# ------------------------------------------------------------------
# Add + field round trip
# ------------------------------------------------------------------
def test_add_task_fields_round_trip(tm):
    task, warnings = tm.add_task("Quiz 3", "CS 101", _due(tm, 2), 4,
                                 estimated_hours=2.5, task_type="quiz",
                                 deadline_time="09:30")
    assert warnings == []
    stored = tm._tasks[task.id]
    assert stored.name == "Quiz 3" and stored.subject == "CS 101"
    assert stored.estimated_hours == 2.5 and stored.task_type == "quiz"
    assert stored.deadline_time == "09:30"
    assert task.id in {e[3].id for e in tm._heap.to_list()}   # heap has it
    assert tm._avl.contains(task.id)                          # AVL has it


def test_add_past_date_warns_but_stores(tm):
    task, warnings = tm.add_task("Late thing", "CS", _due(tm, -3), 2)
    assert len(warnings) == 1 and "past" in warnings[0]
    assert task.id in tm._tasks and not task.completed


# ------------------------------------------------------------------
# Edit
# ------------------------------------------------------------------
def test_edit_updates_fields(tm):
    task, _ = tm.add_task("Draft", "CS", _due(tm, 4), 3)
    edited, _ = tm.edit_task(task.id, "Draft v2", "Math", _due(tm, 4), 2,
                             3.5, "assignment")
    assert edited.name == "Draft v2" and edited.subject == "Math"
    assert edited.difficulty == 2 and edited.estimated_hours == 3.5
    assert edited.task_type == "assignment"


def test_edit_deadline_resorts_both_structures(tm):
    a, _ = tm.add_task("A", "CS", _due(tm, 1), 3)
    b, _ = tm.add_task("B", "CS", _due(tm, 9), 3)
    old = tm._avl.inorder()
    assert old == [a, b]                     # A is earliest now
    tm.edit_task(b.id, "B", "CS", _due(tm, 0), 3, 1.0, "meeting")
    new = tm._avl.inorder()
    assert new == [b, a]                     # B jumped ahead of A
    # the heap keys moved too: B's stored priority must equal a fresh score
    entry = next(e for e in tm._heap.to_list() if e[3].id == b.id)
    fresh = priority_score(tm._tasks[b.id], tm.today())
    assert entry[0] == pytest.approx(fresh, abs=1e-3)                 # re-scored, in place


def test_edit_deadling_only_changes_that_task(tm):
    a, _ = tm.add_task("Anchor", "CS", _due(tm, 5), 3)
    others = [e[3].id for e in tm._heap.to_list()]
    tm.edit_task(a.id, "Anchor", "CS", _due(tm, -2), 3, 1.0, "other")
    assert tm._avl.inorder() == [a]          # still exactly one open task


def test_edit_nonexistent_raises(tm):
    with pytest.raises(ValueError, match="does not exist"):
        tm.edit_task(4242, "Ghost", "CS", _due(tm, 5), 3, 1.0, "other")


def test_edit_completed_task_rejected(tm):
    task, _ = tm.add_task("Done already", "CS", _due(tm, 2), 3)
    tm.complete_task(task.id)
    with pytest.raises(ValueError, match="Completed"):
        tm.edit_task(task.id, "X", "CS", _due(tm, 2), 3, 1.0, "other")


def test_edit_validation_rejects(tm):
    task, _ = tm.add_task("Keep me", "CS", _due(tm, 3), 3)
    snapshot = tm._tasks[task.id].name
    with pytest.raises(ValueError):
        tm.edit_task(task.id, "", "CS", _due(tm, 3), 3, 1.0, "other")
    assert tm._tasks[task.id].name == snapshot     # NOTHING was mutated


# ------------------------------------------------------------------
# Complete (soft delete) + restore
# ------------------------------------------------------------------
def test_complete_sets_timestamp_and_stays_in_list(tm):
    task, _ = tm.add_task("Finish me", "CS", _due(tm, 2), 3)
    done = tm.complete_task(task.id)
    assert done.completed is True
    assert done.completed_at                 # ISO timestamp was stamped
    assert task.id in tm._tasks              # NOT hard-deleted
    assert not tm._avl.contains(task.id)     # gone from the tree
    assert not tm._heap.contains(task.id)    # gone from the heap


def test_complete_twice_is_none(tm):
    task, _ = tm.add_task("Once", "CS", _due(tm, 2), 3)
    assert tm.complete_task(task.id) is not None
    assert tm.complete_task(task.id) is None


def test_complete_nonexistent_is_none(tm):
    assert tm.complete_task(4242) is None


def test_complete_top_pops_heap(tm):
    a, _ = tm.add_task("Less", "CS", _due(tm, 9), 1)
    b, _ = tm.add_task("More", "CS", _due(tm, 0), 5)   # more urgent
    done = tm.complete_top()
    assert done is b                          # the heap's top popped


def test_restore_returns_task_to_both_structures(tm):
    task, _ = tm.add_task("Come back", "CS", _due(tm, 2), 3)
    tm.complete_task(task.id)
    got = tm.restore_task(task.id)
    assert got.completed is False and got.completed_at is None
    assert tm._avl.contains(task.id)          # tree again
    assert tm._heap.contains(task.id)         # heap again
    assert tm.restore_task(task.id) is None   # not completed -> nothing to do


def test_restore_nonexistent_is_none(tm):
    assert tm.restore_task(4242) is None


# ------------------------------------------------------------------
# Persistence (SQLite) + migration
# ------------------------------------------------------------------
def test_persistence_across_managers(tmp_path):
    db = str(tmp_path / "persist.db")
    first = TaskManager(db)
    task, _ = first.add_task("Survive restart", "CS",
                             (first.today() + timedelta(days=4)).isoformat(), 3,
                             estimated_hours=2.0, task_type="quiz")
    first.complete_task(task.id)              # completed tasks persist too
    first.store.close()

    second = TaskManager(db)
    try:
        assert "Survive restart" in {t.name for t in second._tasks.values()}
        reloaded = next(t for t in second._tasks.values() if t.id == task.id)
        assert reloaded.completed is True and reloaded.estimated_hours == 2.0
    finally:
        second.store.close()


def test_migration_imports_tasks_json(tmp_path):
    db = str(tmp_path / "migrate.db")
    legacy = tmp_path / "tasks.json"
    legacy.write_text(json.dumps({
        "next_id": 3,
        "tasks": [
            {"id": 1, "name": "Old quiz", "subject": "CS", "deadline": "2026-11-01",
             "difficulty": 3},
            {"id": 2, "name": "Old meeting", "subject": "CS",
             "deadline": "2026-10-25", "difficulty": 2,
             "task_type": "meeting", "deadline_time": "14:00"},
        ]}), encoding="utf-8")

    # _fresh triggers the import; pass our OWN legacy path (never the
    # developer's real nextup/tasks.json!).
    manager = TaskManager(db, legacy_json=str(legacy))
    try:
        names = {t.name for t in manager._tasks.values()}
        assert names == {"Old quiz", "Old meeting"}
        meeting = next(t for t in manager._tasks.values()
                       if t.name == "Old meeting")
        assert meeting.task_type == "activity"   # legacy 'meeting' migrated cleanly
        assert meeting.deadline_time == "14:00"   # new fields survive migration
        assert manager._next_id >= 3              # ids never reused
        # running it twice must be a no-op (same manager object, no dupes)
        imported = manager.store.migrate_from_json(str(legacy))
        assert imported == 0
    finally:
        manager.store.close()


def test_delete_all_then_restart_does_not_resurrect_legacy(tmp_path):
    """Regression: freshness is judged by the TABLE's existence, not the
    row count. The user may legitimately hard-delete every task via the
    /delete route; on the next startup the (now empty) database must NOT
    look brand-new, or TaskManager would re-run the legacy tasks.json
    migration and resurrect exactly the tasks the user chose to delete.
   """
    db = str(tmp_path / "emptied.db")
    legacy = tmp_path / "tasks.json"
    legacy.write_text(json.dumps({
        "tasks": [{"id": 1, "name": "Ghost", "subject": "CS",
                   "deadline": "2026-11-01", "difficulty": 3}]}),
                  encoding="utf-8")

    first = TaskManager(db, legacy_json=str(legacy))
    try:
        assert len(first._tasks) == 1          # migration ran, as expected
        first.complete_task(1)
        first.delete_task(1)                   # /delete route: rows -> 0
        assert len(first._tasks) == 0
    finally:
        first.store.close()

    second = TaskManager(db, legacy_json=str(legacy))
    try:
        assert len(second._tasks) == 0         # 'Ghost' stays in the trash
        assert second.store._fresh is False    # and it is not a new database
    finally:
        second.store.close()


def test_next_id_never_reused(tmp_path):
    db = str(tmp_path / "ids.db")
    first = TaskManager(db)
    t1, _ = first.add_task("One", "CS", (first.today() + timedelta(days=1)).isoformat(), 3)
    t2, _ = first.add_task("Two", "CS", (first.today() + timedelta(days=2)).isoformat(), 3)
    first.complete_task(t2.id)
    first.store.close()
    second = TaskManager(db)
    try:
        t3, _ = second.add_task("Three", "CS",
                                (second.today() + timedelta(days=3)).isoformat(), 3)
        assert t3.id > t2.id                   # completed ids are NOT recycled
    finally:
        second.store.close()
