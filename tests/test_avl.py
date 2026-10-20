"""
test_avl.py
===========
Plain-assert tests for the hand-built AVL tree. Run directly:

    python test_avl.py        (from inside the nextup/ folder)

20 checks, no test framework needed. Highlights: the 500-task
sorted-deadline insert that must keep the height near log2(500) ~ 9,
duplicate deadlines, all four rotations, deletes that keep the tree a
valid AVL, and the O(1) stats + find_kth + range_query data layer.
"""

from datetime import date, timedelta

from avl_tree import AVLTree
from task import Task

TODAY = date(2026, 10, 20)
TICKS = 0


def _task(days, name="t", subject="CS"):
    """A Task due `days` days from TODAY, with a unique auto-minted id."""
    global TICKS
    TICKS += 1
    return Task(task_id=TICKS, name=f"{name}{TICKS}", subject=subject,
                deadline=TODAY + timedelta(days=days), difficulty=(TICKS % 5) + 1)


def _log2(n):
    from math import log2
    return log2(n)


# 1. Empty tree: nothing stored, inorder empty, height 0.
tree = AVLTree()
assert len(tree) == 0 and tree.inorder() == [] and tree.height() == 0
print("1/20 empty tree OK")

# 2. Single insert: height 1, inorder has exactly that task.
solo = _task(3)
tree.insert(solo)
assert len(tree) == 1 and tree.height() == 1 and tree.inorder() == [solo]
print("2/20 single insert OK")

# 3. Duplicate deadlines are ALLOWED: same day, different ids -- both stored.
tree = AVLTree()
d1, d2 = _task(5), _task(5)
tree.insert(d1); tree.insert(d2)
got = tree.inorder()
assert len(got) == 2 and got[0] is d1 and got[1] is d2     # id tie-break inside a day
print("3/20 duplicate deadlines kept OK")

# 4. Inorder is sorted earliest -> latest deadline (the Sorted Task View rule).
tree = AVLTree()
out_of_order = [10, -2, 3, 0, 7, -5, 1]
tasks = [_task(d) for d in out_of_order]
for t in tasks:
    tree.insert(t)
assert [t.deadline for t in tree.inorder()] == [t.deadline for t in sorted(tasks, key=lambda x: x.deadline)]
print("4/20 inorder is deadline-sorted OK")

# 5. Sorted (adversarial) inserts: a plain BST would become a linked list
#    (height 99); the AVL must stay near log2(100) ~ 6.6.
tree = AVLTree()
for d in range(100):                      # increasing deadlines = worst case
    tree.insert(_task(d))
assert tree.is_avl()
assert tree.height() <= _log2(100) + 2    # ~8.6 allowed, expect 6 or 7
print(f"5/20 100 sorted inserts -> height {tree.height()} (log2(100)~6.6) OK")

# 6. LL/RR single-rotation cases handled by sorted inserts from both ends:
tree = AVLTree()
for d in [1, 2, 3, 4, 5, 6, 7]:           # right-right chain -> RR rotations
    tree.insert(_task(d))
assert tree.is_avl() and tree.height() <= 4
tree = AVLTree()
for d in [7, 6, 5, 4, 3, 2, 1]:           # left-left chain -> LL rotations
    tree.insert(_task(d))
assert tree.is_avl() and tree.height() <= 4
print("6/20 LL and RR rotation chains OK")

# 7. LR and RL double rotations: zig-zag insert orders force them.
zig1, zig2 = [0, 2, 1], [0, -2, -1]
for order in (zig1, zig2, [-1, 1, 0], [0, 1, -1]):
    tree = AVLTree()
    for d in order:
        tree.insert(_task(d))
    assert tree.is_avl() and tree.height() == 2   # perfectly balanced zig-zag
print("7/20 LR and RL double rotations OK")

# 8. Delete a LEAF: remaining inorder unchanged apart from that task.
tree = AVLTree()
friends = [_task(d) for d in [5, 2, 8, 1, 3]]
for t in friends:
    tree.insert(t)
tree.delete(friends[3])                            # the earliest one (leaf)
rest = [t for t in sorted(friends[:3] + friends[4:], key=lambda x: x.deadline)]
assert tree.inorder() == rest and tree.is_avl() and not tree.contains(friends[3].id)
print("8/20 delete leaf OK")

# 9. Delete the ROOT (two children): successor takes over, tree still valid.
tree = AVLTree()
tasks9 = [_task(d) for d in [5, 2, 8, 1, 3, 7]]
for t in tasks9:
    tree.insert(t)
survivors = sorted(tasks9[1:], key=lambda x: x.deadline)
tree.delete(tasks9[0])                             # d=5 is the root after inserts
assert tree.inorder() == survivors and tree.is_avl()
print("9/20 delete root (two children) OK")

# 10. Delete a task that is NOT stored: harmless no-op, no crash.
before = tree.inorder()
ghost = _task(99)
tree.delete(ghost)
assert tree.inorder() == before and len(tree) == 5
print("10/20 delete unknown no-op OK")

# 11. THE HEADLINER: 500 tasks with fully SORTED deadlines (worst case for a
#     plain BST) must land near log2(500) ~ 8.97. A plain BST would hit 499.
tree = AVLTree()
for d in range(500):
    tree.insert(_task(d))
assert tree.is_avl()
assert len(tree) == 500
h = tree.height()
assert 8 <= h <= 10, f"height {h} not near log2(500)~8.97"   # 'near': within 1 day
assert [t.deadline for t in tree.inorder()] == sorted(t.deadline for t in tree.inorder())
print(f"11/20 500 sorted inserts -> height {h} (log2(500)=8.97) OK")

# 12. Mixed churn: insert 200, delete 100, insert 100 -- still a valid AVL,
#     still sorted, and the survivors are exactly the expected set.
tree = AVLTree()
tasks = [_task((k * 7) % 61) for k in range(200)]           # deadlines repeat -> dup keys days
for t in tasks:
    tree.insert(t)
for t in tasks[:100]:
    tree.delete(t)
second = [_task((k * 3) % 40) for k in range(100)]
for t in second:
    tree.insert(t)
got = tree.inorder()
expected = sorted(tasks[100:] + second, key=lambda x: (x.deadline, x.id))
assert got == expected and tree.is_avl()
assert all(got[i].deadline <= got[i + 1].deadline for i in range(len(got) - 1))
print(f"12/20 churn (200 ins / 100 del / 100 ins) -> height {tree.height()}, valid OK")

# 13. node_count()/max_depth(): O(1) stats that must agree with the tree.
tree = AVLTree()
assert tree.node_count() == 0 and tree.max_depth() == -1     # empty: -1 edges
solo = _task(4)
tree.insert(solo)
assert tree.node_count() == 1 and tree.max_depth() == 0      # 1 node, 0 edges
for d in [2, 6, 1, 8]:                                       # 4 more tasks
    tree.insert(_task(d))
assert tree.node_count() == 5
assert tree.max_depth() == tree.height() - 1                 # depth = height - 1
tree.delete(solo)
assert tree.node_count() == 4 and tree.is_avl()              # size cache still correct
print("13/20 node_count / max_depth OK")

# 14. find_kth(): index 0 = earliest deadline, n-1 = latest -- all kth slots
#     must match the sorted order, WITHOUT building the inorder list.
tree = AVLTree()
tasks = [_task(d) for d in [7, -3, 0, 12, 4]]                # shuffled deadlines
for t in tasks:
    tree.insert(t)
expected = sorted(tasks, key=lambda x: x.deadline)
for k in range(len(tasks)):
    assert tree.find_kth(k) is expected[k]                   # same OBJECT, not just equal
print("14/20 find_kth matches sorted order OK")

# 15. find_kth() with DUPLICATE deadlines: ties broken by task id, exactly
#     like the inorder traversal would order them.
tree = AVLTree()
a, b, c = _task(5), _task(5), _task(5)                       # ids ascend: a < b < c
tree.insert(b); tree.insert(c); tree.insert(a)               # insert in shuffled order
assert tree.find_kth(0) is a
assert tree.find_kth(1) is b
assert tree.find_kth(2) is c
print("15/20 find_kth breaks duplicate-deadline ties by id OK")

# 16. find_kth() rejects out-of-range k with IndexError (like a Python list).
tree = AVLTree()
tree.insert(_task(1))
for bad_k in [-1, 1, 100]:
    try:
        tree.find_kth(bad_k)
        assert False, f"k={bad_k} should have raised IndexError"
    except IndexError:
        pass                                                 # exactly what we wanted
print("16/20 find_kth out-of-range raises IndexError OK")

# 17. find_kth() stays correct after DELETIONS (the size cache keeps up).
tree = AVLTree()
tasks = [_task(d) for d in range(10)]                        # deadlines 0..9 in order
for t in tasks:
    tree.insert(t)
tree.delete(tasks[2]); tree.delete(tasks[7])
survivors = [t for t in tasks if t.id not in (tasks[2].id, tasks[7].id)]
for k in range(8):
    assert tree.find_kth(k) is survivors[k]                  # survivors stay sorted
assert tree.node_count() == 8 and tree.is_avl()
print("17/20 find_kth after deletes OK")

# 18. range_query(): only tasks with start <= deadline <= end, in order.
tree = AVLTree()
tasks = [_task(d) for d in [30, -5, 0, 14, 7, 21, 3]]        # TODAY-5 .. TODAY+30
for t in tasks:
    tree.insert(t)
lo, hi = TODAY + timedelta(days=3), TODAY + timedelta(days=21)
hits = tree.range_query(lo, hi)
expected = sorted([t for t in tasks if lo <= t.deadline <= hi],
                  key=lambda x: (x.deadline, x.id))
assert hits == expected
assert tree.node_count() == 7                               # the query did not eat the tree
print("18/20 range_query window OK")

# 19. range_query() boundaries are INCLUSIVE on both ends -- a task sitting
#     exactly on each edge must be returned -- and an empty window is [].
tree = AVLTree()
edge_lo, edge_hi = _task(5), _task(5)                        # both ON the boundary day
inside, outside = _task(4), _task(6)
for t in (edge_lo, outside, edge_hi, inside):
    tree.insert(t)
edge_day = TODAY + timedelta(days=5)
assert tree.range_query(edge_day, edge_day) == [edge_lo, edge_hi]   # ids ascend
assert tree.range_query(TODAY + timedelta(days=100),
                        TODAY + timedelta(days=200)) == []   # window misses everything
print("19/20 range_query inclusive boundaries + empty window OK")

# 20. range_query() over 300 tasks must match a brute-force filter, and an
#     inverted window (start > end) is simply empty, not an error.
tree = AVLTree()
tasks = [_task(k % 40) for k in range(300)]                  # 300 tasks, 40 distinct days
for t in tasks:
    tree.insert(t)
lo, hi = TODAY + timedelta(days=10), TODAY + timedelta(days=25)
hits = tree.range_query(lo, hi)
brute = sorted([t for t in tasks if lo <= t.deadline <= hi],
               key=lambda x: (x.deadline, x.id))
assert hits == brute
assert tree.range_query(hi, lo) == []                        # start > end -> empty
print("20/20 range_query on 300 tasks matches brute force OK")

print("ALL 20 AVL TESTS PASSED")
