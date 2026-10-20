"""
heap.py — Hand-built Max-Heap with an O(1) position map (_pos: task_id -> index).

Entry tuple: (priority, -deadline_ord, -task_id, task)
Complexity: peek/contains O(1); insert/extract_max/remove/update_priority O(log n); build O(n).
"""


class MaxHeap:
    """Array-backed max-heap of (priority, -deadline_ord, -task_id, task) tuples."""

    def __init__(self):
        self._items = []
        self._pos = {}  # task_id -> index in _items

    @staticmethod
    def _parent(i: int) -> int:
        return (i - 1) // 2

    @staticmethod
    def _left(i: int) -> int:
        return 2 * i + 1

    @staticmethod
    def _right(i: int) -> int:
        return 2 * i + 2

    def __len__(self) -> int:
        return len(self._items)

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def peek(self):
        """Return highest-priority task without removing it, or None. O(1)."""
        return None if self.is_empty() else self._items[0][3]

    def peek_priority(self):
        """Return top task's priority score, or None. O(1)."""
        return None if self.is_empty() else self._items[0][0]

    @staticmethod
    def make_key(task, priority):
        """Build comparable entry tuple; negatives break ties by earlier deadline then smaller id. O(1)."""
        return (priority, -task.deadline.toordinal(), -task.id, task)

    def _swap(self, i: int, j: int) -> None:
        """Swap two slots and keep _pos synchronized. O(1)."""
        self._items[i], self._items[j] = self._items[j], self._items[i]
        self._pos[self._items[i][3].id] = i
        self._pos[self._items[j][3].id] = j

    def _sift_up(self, i: int) -> None:
        """Bubble node i up until heap property holds. O(log n)."""
        while i > 0:
            p = self._parent(i)
            if self._items[i] > self._items[p]:
                self._swap(i, p)
                i = p
            else:
                break

    def _sift_down(self, i: int) -> None:
        """Sink node i down until it beats both children. O(log n)."""
        n = len(self._items)
        while True:
            best = i
            l, r = self._left(i), self._right(i)
            if l < n and self._items[l] > self._items[best]:
                best = l
            if r < n and self._items[r] > self._items[best]:
                best = r
            if best == i:
                return
            self._swap(i, best)
            i = best

    def insert(self, task, priority) -> None:
        """Insert a task with its precomputed priority. O(log n)."""
        self._items.append(self.make_key(task, priority))
        last = len(self._items) - 1
        self._pos[task.id] = last
        self._sift_up(last)

    def build(self, entries) -> None:
        """Floyd's bottom-up heapify from an iterable of key tuples. O(n)."""
        self._items = list(entries)
        self._pos = {entry[3].id: i for i, entry in enumerate(self._items)}
        for i in range(len(self._items) // 2 - 1, -1, -1):
            self._sift_down(i)

    def extract_max(self):
        """Pop and return the highest-priority task, or None. O(log n)."""
        if self.is_empty():
            return None
        top = self._items[0][3]
        del self._pos[top.id]
        last = self._items.pop()
        if self._items:
            self._pos[last[3].id] = 0
            self._items[0] = last
            self._sift_down(0)
        return top

    def remove(self, task_id):
        """Remove any task by id via _pos lookup and re-sift. O(log n)."""
        i = self._pos.get(task_id)
        if i is None:
            return None
        found = self._items[i]
        del self._pos[task_id]
        last = self._items.pop()
        if i < len(self._items):
            self._pos[last[3].id] = i
            self._items[i] = last
            self._sift_down(i)
            self._sift_up(i)
        return found[3]

    def update_priority(self, task_id, priority):
        """Update a queued task's score in place and re-sift. O(log n)."""
        i = self._pos.get(task_id)
        if i is None:
            return False
        task = self._items[i][3]
        self._items[i] = self.make_key(task, priority)
        self._sift_down(i)
        self._sift_up(i)
        return True

    def contains(self, task_id) -> bool:
        """True if task_id is in the heap. O(1)."""
        return task_id in self._pos

    def to_list(self):
        """Return shallow copy of raw heap entries. O(n)."""
        return list(self._items)

    def export_json(self):
        """Read-only export of array slots for the visualizer page. O(n)."""
        return [{"index": i, "name": e[3].name, "priority": round(e[0], 1),
                 "deadline": e[3].deadline_str(), "task_type": e[3].task_type}
                for i, e in enumerate(self._items)]
