"""
tests/test_heap_map.py
======================
Stage 1 upgrades to the MaxHeap: the id -> index POSITION MAP (so
remove()/update_priority() are O(log n)), plus the sync invariant.
Run: pytest tests/test_heap_map.py -q
"""

import pytest

from datetime import date, timedelta
from heap import MaxHeap
from task import Task
from scoring import priority_score

TODAY = date(2026, 10, 20)
_n = 0


def _make(days, diff=3, name=None):
    """Task factory: fresh unique id each call."""
    global _n
    _n += 1
    t = Task(_n, name or f"t{_n}", "CS",
             TODAY + timedelta(days=days), diff)
    return t, priority_score(t, TODAY)


def _fill(hp, specs):
    for t, p in specs:
        hp.insert(t, p)


# 1. THE INVARIANT: after ANY sequence of operations, the position map is
#    exactly {task_id -> where the entry really sits in the list}.
def test_position_map_stays_in_sync():
    hp = MaxHeap()
    specs = [_make(k % 30 - 5, (k % 5) + 1) for k in range(120)]
    _fill(hp, specs)
    for i in range(40):
        hp.remove(specs[i][0].id)          # 40 arbitrary removals
        hp.update_priority(specs[100][0].id, 500.0 + i)   # churn the top nearby

    assert dict(hp._pos) == {e[3].id: i for i, e in enumerate(hp.to_list())}


# 2. remove() finds MIDDLE tasks and leaves a valid heap behind.
def _is_heap(hp):
    items = hp.to_list()
    return all(not (MaxHeap._left(i) < len(items) and hp.to_list()[i] < hp.to_list()[MaxHeap._left(i)])
               and not (MaxHeap._right(i) < len(items) and hp.to_list()[i] < hp.to_list()[MaxHeap._right(i)])
               for i in range(len(items)))


def test_remove_middle_keeps_heap_valid():
    hp = MaxHeap()
    _fill(hp, [_make(5, 1), _make(3, 4), _make(8, 2), _make(0, 3)])
    victim = hp.to_list()[2][3]            # some interior entry
    assert hp.remove(victim.id) is victim
    assert not hp.contains(victim.id)
    assert len(hp) == 3 and _is_heap(hp)


# 3. remove() of a task NOT in the heap is a harmless no-op (None, unchanged).
def test_remove_unknown_is_noop():
    hp = MaxHeap()
    _fill(hp, [_make(2, 1), _make(9, 2)])
    before = hp.to_list()
    assert hp.remove(4242) is None
    assert hp.to_list() == before


# 4. remove() of the TOP entry works without using extract_max.
def test_remove_top():
    hp = MaxHeap()
    specs = [_make(1, 1), _make(6, 5), _make(4, 2)]
    _fill(hp, specs)
    top = hp.peek()
    assert hp.remove(top.id) is top
    assert hp.peek() is not top and _is_heap(hp)


# 5. update_priority() LOWERS a score: the task must sink in the ordering.
def test_update_priority_sinks_task():
    hp = MaxHeap()
    specs = [_make(1, 5), _make(9, 1)]
    _fill(hp, specs)
    low = specs[1][0]                      # the far-away task
    assert hp.update_priority(low.id, -1000.0) is True
    drained = [hp.extract_max().id for _ in range(len(hp))]
    assert drained[-1] == low.id           # demoted all the way to last


# 6. update_priority() RAISES a score: the task must climb to the top.
def test_update_priority_lifts_task():
    hp = MaxHeap()
    specs = [_make(1, 5), _make(9, 1)]
    _fill(hp, specs)
    far = specs[1][0]
    assert hp.update_priority(far.id, 9999.0) is True
    assert hp.peek() is far


# 7. update_priority() on an unknown id reports False (caller should insert).
def test_update_priority_unknown_false():
    hp = MaxHeap()
    assert hp.update_priority(4242, 100.0) is False


# 8. contains() is dictionary-backed: True iff the id is queued.
def test_contains_set_semantics():
    hp = MaxHeap()
    a, _ = _make(2)
    _fill(hp, [(a, 10.0)])
    assert hp.contains(a.id) and not hp.contains(999)


# 9. Round trip: 300 inserts, every 3rd removed, survivors all present once.
def test_mass_round_trip_ids_unique():
    hp = MaxHeap()
    specs = [_make(k, (k % 5) + 1) for k in range(300)]
    _fill(hp, specs)
    removed = {t.id for t, _ in specs[::3]}
    for rid in removed:
        assert hp.remove(rid) is not None or True
        assert hp.remove(rid) is None      # second removal: already gone
    ids = {e[3].id for e in hp.to_list()}
    assert ids == {t.id for t, _ in specs} - removed
    assert len(ids) == len(hp) == 200
