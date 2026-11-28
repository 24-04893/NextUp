"""
avl_tree.py — Self-balancing AVL Tree keyed by (deadline.toordinal(), task_id).

Maintains balance factor in {-1, 0, +1} via LL, RR, LR, and RL rotations.
Complexity: insert/delete/search/find_kth O(log n); inorder O(n); range_query O(log n + m).
"""

from datetime import date

if __package__:
    from .event_queue import EventQueue
else:
    from event_queue import EventQueue


class _Node:
    """AVL tree node storing key, task payload, cached height, and subtree size."""

    __slots__ = ("key", "task", "left", "right", "height", "size")

    def __init__(self, key, task):
        self.key = key
        self.task = task
        self.left = None
        self.right = None
        self.height = 1
        self.size = 1


def _height(node):
    return node.height if node is not None else 0


def _size(node):
    return node.size if node is not None else 0


def _update_node(node):
    """Recompute cached height and subtree size from children. O(1)."""
    node.height = 1 + max(_height(node.left), _height(node.right))
    node.size = 1 + _size(node.left) + _size(node.right)


def _balance_factor(node):
    """Return height(left) - height(right). O(1)."""
    if node is None:
        return 0
    return _height(node.left) - _height(node.right)


class AVLTree:
    """Self-balancing BST keyed by (deadline, task_id)."""

    def __init__(self):
        self._root = None
        self.visited = 0    # nodes touched by last range_query
        self.log = EventQueue(max_size=20)
        self.mute = False   # suppress event logging during full rebuilds

    @staticmethod
    def _rotate_right(y):
        """LL rotation: lift left child x above y. O(1)."""
        x = y.left
        y.left = x.right
        x.right = y
        _update_node(y)  # y is now lower, update first
        _update_node(x)
        return x

    @staticmethod
    def _rotate_left(x):
        """RR rotation: lift right child y above x. O(1)."""
        y = x.right
        x.right = y.left
        y.left = x
        _update_node(x)
        _update_node(y)
        return y

    def _record(self, op, name):
        """Enqueue event into bounded FIFO log unless muted. O(1)."""
        if self.mute:
            return
        self.log.enqueue({"op": op, "name": str(name)})

    def insert(self, task):
        """Insert task and rebalance ancestors. O(log n)."""
        key = (task.deadline.toordinal(), task.id)
        self._root = self._insert(self._root, key, task)
        self._record("insert", task.name)

    def _insert(self, node, key, task):
        if node is None:
            return _Node(key, task)
        if key < node.key:
            node.left = self._insert(node.left, key, task)
        elif key > node.key:
            node.right = self._insert(node.right, key, task)
        else:
            raise ValueError(f"duplicate key {key} -- task id {key[1]} already inserted")
        return self._rebalance(node)

    def delete(self, task):
        """Delete task by key and rebalance ancestors (no-op if absent). O(log n)."""
        if self.search(task) is None:
            return
        key = (task.deadline.toordinal(), task.id)
        self._root = self._delete(self._root, key)
        self._record("delete", task.name)

    def _delete(self, node, key):
        if node is None:
            return None
        if key < node.key:
            node.left = self._delete(node.left, key)
        elif key > node.key:
            node.right = self._delete(node.right, key)
        else:
            if node.left is None:
                return node.right
            if node.right is None:
                return node.left
            # Two children: replace with in-order successor (leftmost in right subtree).
            succ = node.right
            while succ.left is not None:
                succ = succ.left
            node.key, node.task = succ.key, succ.task
            node.right = self._delete(node.right, succ.key)
        return self._rebalance(node)

    def _rebalance(self, node):
        """Restore AVL balance {-1, 0, +1} using LL, LR, RR, or RL rotation. O(1)."""
        _update_node(node)
        balance = _balance_factor(node)

        if balance > 1:
            if _balance_factor(node.left) >= 0:
                self._record("LL", node.task.name)
                return self._rotate_right(node)
            self._record("LR", node.task.name)
            node.left = self._rotate_left(node.left)
            return self._rotate_right(node)

        if balance < -1:
            if _balance_factor(node.right) <= 0:
                self._record("RR", node.task.name)
                return self._rotate_left(node)
            self._record("RL", node.task.name)
            node.right = self._rotate_right(node.right)
            return self._rotate_left(node)

        return node

    def search(self, task):
        """Return node matching task's key, or None. O(log n)."""
        key = (task.deadline.toordinal(), task.id)
        node = self._root
        while node is not None:
            if key == node.key:
                return node
            node = node.left if key < node.key else node.right
        return None

    def contains(self, task_id):
        """True if any node holds task_id (debug helper). O(n)."""
        for node in self._all_nodes():
            if node.task.id == task_id:
                return True
        return False

    def inorder(self):
        """Return all tasks sorted from earliest to latest deadline. O(n)."""
        out = []
        self._inorder(self._root, out)
        return out

    def _inorder(self, node, out):
        if node is None:
            return
        self._inorder(node.left, out)
        out.append(node.task)
        self._inorder(node.right, out)

    def find_kth(self, k):
        """Return k-th task in deadline order (0-indexed) using cached subtree sizes. O(log n)."""
        if k < 0 or k >= _size(self._root):
            raise IndexError(f"k={k} out of range for {self.node_count()} tasks")
        node = self._root
        while True:
            left_size = _size(node.left)
            if k < left_size:
                node = node.left
            elif k == left_size:
                return node.task
            else:
                k -= left_size + 1
                node = node.right

    def range_query(self, start, end):
        """Return tasks with start <= deadline <= end in order, pruning out-of-range subtrees. O(log n + m)."""
        lo, hi = start.toordinal(), end.toordinal()
        if lo > hi:
            return []
        out = []
        self.visited = 0
        self._range(self._root, lo, hi, out)
        return out

    def _range(self, node, lo, hi, out):
        if node is None:
            return
        self.visited += 1
        d = node.key[0]
        if lo <= d:
            self._range(node.left, lo, hi, out)
        if lo <= d <= hi:
            out.append(node.task)
        if d <= hi:
            self._range(node.right, lo, hi, out)

    def _all_nodes(self):
        """Pre-order list of all nodes (debug helper). O(n)."""
        out = []
        stack = [self._root] if self._root else []
        while stack:
            node = stack.pop()
            out.append(node)
            if node.right:
                stack.append(node.right)
            if node.left:
                stack.append(node.left)
        return out

    def height(self):
        """Cached tree height (0 empty, 1 single node). O(1)."""
        return _height(self._root)

    def max_depth(self):
        """Deepest edge depth (-1 empty, 0 single node). O(1)."""
        return _height(self._root) - 1

    def node_count(self):
        """Cached number of stored tasks. O(1)."""
        return _size(self._root)

    def __len__(self):
        return _size(self._root)

    def export_json(self):
        """Read-only nested-dict export for the visualizer SVG. O(n)."""
        return self._export(self._root)

    def _export(self, node):
        if node is None:
            return None
        return {"name": node.task.name,
                "deadline": node.task.deadline_str(),
                "balance": _balance_factor(node),
                "left": self._export(node.left),
                "right": self._export(node.right)}

    def is_avl(self):
        """Verify AVL balance and cached height/size invariants across all nodes. O(n)."""
        for node in self._all_nodes():
            if abs(_balance_factor(node)) > 1:
                return False
            if node.height != 1 + max(_height(node.left), _height(node.right)):
                return False
            if node.size != 1 + _size(node.left) + _size(node.right):
                return False
        return True
