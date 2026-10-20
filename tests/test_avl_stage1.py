"""
tests/test_avl_stage1.py
========================
AVL requirements from stage 1 that the standalone test_avl.py does not
already cover: insert/delete basics, the 500 sorted inserts balance
check, duplicate deadlines, and the heap/AVL sync checks.
Run: pytest tests/test_avl_stage1.py -q
"""

import pytest

from datetime import date, timedelta
from avl_tree import AVLTree
from task import Task

TODAY = date(2026, 10, 20)
_n = 0


def _make(days):
    global _n
    _n += 1
    return Task(_n, f"t{_n}", "CS", TODAY + timedelta(days=days), 3)


# 1. THE HEADLINER: 500 already-SORTED inserts (a plain BST becomes a
#    linked list here) must still land near log2(500) ~ 8.97.
def test_500_sorted_inserts_stay_balanced():
    tree = AVLTree()
    for d in range(500):                    # strictly increasing deadlines
        tree.insert(_make(d))
    assert tree.is_avl()                    # every balance factor in range
    assert tree.node_count() == 500
    assert 8 <= tree.height() <= 10         # a plain BST would be 500 / 499


# 2. Inorder is always deadline-sorted, earliest first.
def test_inorder_is_deadline_sorted():
    tree = AVLTree()
    days = [30, -5, 0, 14, 7, 21, 3]
    for d in days:
        tree.insert(_make(d))
    dl = [t.deadline for t in tree.inorder()]
    assert dl == sorted(dl) and len(dl) == len(days)


# 3. Deleting re-balances and really removes the task.
def test_delete_removes_and_rebalances():
    tree = AVLTree()
    tasks = [_make(d) for d in [5, 2, 8, 1, 3]]
    for t in tasks:
        tree.insert(t)
    tree.delete(tasks[0])                   # due +5 -- somewhere in the middle
    got = tree.inorder()
    assert tasks[0] not in got and len(got) == 4 and tree.is_avl()
    tree.delete(tasks[0])                   # second delete: harmless no-op
    assert tree.node_count() == 4


# 4. DUPLICATE deadlines coexist (the id makes the key total), ties by id.
def test_duplicate_deadlines_coexist():
    tree = AVLTree()
    a, b, c = _make(5), _make(5), _make(5)  # ids ascend with creation order
    for t in (b, c, a):                     # deliberately shuffled inserts
        tree.insert(t)
    assert tree.inorder() == [a, b, c]      # same day -> ordered by id


# 5. find_kth() agrees with the sorted order for every index.
def test_find_kth_matches_sorted():
    tree = AVLTree()
    tasks = [_make(d) for d in [7, -3, 0, 12, 4]]
    for t in tasks:
        tree.insert(t)
    expected = sorted(tasks, key=lambda x: x.deadline)
    assert all(tree.find_kth(k) is expected[k] for k in range(5))
    with pytest.raises(IndexError):
        tree.find_kth(5)


# 6. range_query(): inclusive window, matches a brute-force filter, and
#    inverted windows are empty.
def test_range_query_window():
    tree = AVLTree()
    tasks = [_make(d) for d in [30, -5, 0, 14, 7, 21, 3, 10, 15]]
    for t in tasks:
        tree.insert(t)
    lo, hi = TODAY + timedelta(days=3), TODAY + timedelta(days=15)
    hits = tree.range_query(lo, hi)
    brute = sorted([t for t in tasks if lo <= t.deadline <= hi],
                   key=lambda x: (x.deadline, x.id))
    assert hits == brute
    assert tree.range_query(hi, lo) == []   # inverted: empty, not a crash


# 7. After deletes, the size cache must be exactly right (find_kth and
#    node_count read it).
def test_size_cache_tracks_deletes():
    tree = AVLTree()
    tasks = [_make(d) for d in range(12)]
    for t in tasks:
        tree.insert(t)
    for t in tasks[:6]:
        tree.delete(t)
    assert tree.node_count() == 6 and len(tree) == 6
    survivors = sorted(tasks[6:], key=lambda x: x.deadline)
    assert [tree.find_kth(k) for k in range(6)] == survivors
    assert tree.is_avl() and tree.height() <= 4   # log2(6)+1 ~ 3.6
