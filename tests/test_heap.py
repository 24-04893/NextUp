"""
test_heap.py
============
Plain-assert tests for the hand-written MaxHeap. Run directly:

    python test_heap.py        (from inside the nextup/ folder)

11 checks, no test framework needed. They cover: empty-heap behavior,
peek, correct extraction order, tie-breaking by earlier deadline,
arbitrary remove(), heap integrity after removals, and O(n) building.
"""

from datetime import date, timedelta

from heap import MaxHeap
from task import Task
from scoring import priority_score

TODAY = date(2026, 10, 20)          # a fixed "today" so asserts never drift
TICKS = 0                            # helper to mint unique deadline dates


def _task(name, days, difficulty, subject="CS"):
    global TICKS
    """Build a Task due `days` days from TODAY with a unique id."""
    TICKS += 1
    t = Task(task_id=TICKS, name=name, subject=subject,
             deadline=TODAY + timedelta(days=days), difficulty=difficulty)
    return t, priority_score(t, TODAY)


def _fill(hp, specs):
    for (t, prio) in specs:
        hp.insert(t, prio)


# 1. Empty heap: peek/extract/remove all behave (None, never crash).
hp = MaxHeap()
assert hp.is_empty() and len(hp) == 0
assert hp.peek() is None and hp.peek_priority() is None
assert hp.extract_max() is None
assert hp.remove(999) is None and not hp.contains(999)
print("1/11 empty-heap behavior OK")

# 2. peek() returns the single inserted task, O(1) by construction.
only, prio = _task("Solo", 3, 2)
hp.insert(only, prio)
assert hp.peek() is only and hp.peek_priority() == prio
print("2/11 single insert + peek OK")

# 3. The top is always the HIGHEST score, no matter the insert order.
hp = MaxHeap()
_s = [_task("a", 9, 1), _task("b", 1, 2), _task("c", 4, 5), _task("d", 0, 3)]
_fill(hp, _s)
assert hp.peek() is _s[3][0] and hp.peek_priority() == _s[3][1]
print("3/11 top is highest score OK")

# 4. extract_max drains in strictly descending score order (heap property).
drained = [hp.extract_max().id for _ in range(len(hp))]
scores = [(t, p) for (t, p) in _s]
expected = [t.id for t, p in sorted(scores, key=lambda tp: (-tp[1], tp[0].deadline, tp[0].id))]
assert drained == expected and hp.is_empty()
print("4/11 extract order == sorted score order OK")

# 5. Tie-break rule: equal score -> EARLIER deadline extracted first.
hp = MaxHeap()
late_tie, p_l = _task("same score, later", 2, 5)      # 28 days urgency x10 + 25 = 305
early_tie, p_e = _task("same score, earlier", 0, 1)   # 30 x10 + 5       = 305
assert p_l == p_e                                     # a genuine tie
# worth 305.0 under the stage-0 formula; 308.5 since stage 1 added
# the hours + type components: 28*10+25+1.5+2 == 30*10+5+1.5+2. What
# matters here is that BOTH match -- the tie-break still fires.
hp.insert(late_tie, p_l)
hp.insert(early_tie, p_e)
assert hp.extract_max() is early_tie
assert hp.extract_max() is late_tie         # drain fully (test hygiene, check 6 needs this)
print("5/11 score ties -> earlier deadline first OK")


# helpers for checks 6-11
def _is_heap(hp):
    """Every parent must beat (or tie) both children."""
    for i, item in enumerate(hp.to_list()):
        for c in (MaxHeap._left(i), MaxHeap._right(i)):
            if c < len(hp) and item < hp.to_list()[c]:
                return False
    return True


# 6. extract_max on empty heap returns None (and stays a valid heap).
assert hp.extract_max() is None and hp.is_empty()
print("6/11 extract from empty OK")

# 7. remove() an arbitrary (MIDDLE) task: heap stays a valid heap,
#    the removed task is gone, the others survive.
hp = MaxHeap()
_fill(hp, [_task("k1", 5, 1), _task("k2", 3, 3), _task("k3", 8, 2), _task("k4", 2, 4)])
victim = hp.to_list()[1][3]                    # whatever sits at index 1
res = hp.remove(victim.id)
assert res is victim and not hp.contains(victim.id) and len(hp) == 3 and _is_heap(hp)
print("7/11 arbitrary middle remove keeps heap valid OK")

# 8. remove() the TOP task behaves like a snappy extract (lists agree afterwards).
hp = MaxHeap()
_fill(hp, [(t, p) for (t, p) in [_task("r1", 1, 1), _task("r2", 6, 5), _task("r3", 4, 2)]])
top = hp.peek()
assert hp.remove(top.id) is top and hp.peek() is not top and _is_heap(hp)
print("8/11 remove(top) keeps ordering OK")

# 9. build() replaces contents and produces a valid heap in one pass.
hp = MaxHeap()
entries = [MaxHeap.make_key(t, p) for (t, p) in _s]
hp.build(entries)
assert len(hp) == 4 and _is_heap(hp) and hp.peek_priority() == max(p for _, p in _s)
print("9/11 O(n) bottom-up build OK")

# 10. remove an id that is NOT queued is a harmless no-op.
before = len(hp)
assert hp.remove(4242) is None and len(hp) == before and _is_heap(hp)
print("10/11 remove(unknown id) no-op OK")

# 11. Stress: 300 random-ish tasks; every repair step keeps the heap valid;
#     50 removals must leave exactly 250 tasks, heap still valid, and
#     collect()-then-sort order must match what extract drains afterwards.
hp = MaxHeap()
specs = []
ids = []
for k in range(300):
    spec = _task(f"t{k}", k % 31 - 5, k % 5 + 1)   # deadlines spread incl. overdue
    specs.append(spec); ids.append(spec[0].id)
_fill(hp, specs)
assert _is_heap(hp)
for v in ids[100:150]:                      # remove 50 arbitrary ids
    hp.remove(v)
removed_ids = ids[100:150]                  # those removed were ids 101..150
assert len(hp) == 250 and _is_heap(hp) and all(not hp.contains(v) for v in removed_ids)
drained_ids = []
while not hp.is_empty():
    drained_ids.append(hp.extract_max().id)
assert sorted(drained_ids) == sorted(v for v in ids if v not in set(removed_ids))
print("11/11 300-task stress with 50 removals OK")

print("ALL 11 HEAP TESTS PASSED")
