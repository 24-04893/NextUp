"""
stack.py — Hand-built LIFO Stack for Undo-Delete history.
"""


class UndoStack:
    """Array-backed LIFO stack storing (task, expiry_epoch) entries."""

    def __init__(self):
        self._items = []

    def is_empty(self) -> bool:
        """True when the stack has no entries. O(1)."""
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)

    def push(self, task, expiry: float) -> None:
        """Push a deleted task and its expiry timestamp onto the top. O(1)."""
        self._items.append((task, expiry))

    def peek(self):
        """Return the most recently deleted (task, expiry) without popping, or None. O(1)."""
        return None if self.is_empty() else self._items[-1]

    def pop(self):
        """Pop and return the most recently deleted (task, expiry), or None. O(1)."""
        return None if self.is_empty() else self._items.pop()

    def pop_by_id(self, task_id: int):
        """Pop the entry matching task_id using a temporary stack to preserve LIFO order. O(n)."""
        aux = []
        found = None
        while not self.is_empty():
            item = self._items.pop()
            if item[0].id == task_id and found is None:
                found = item
                break
            aux.append(item)
        while aux:
            self._items.append(aux.pop())
        return found

    def __getitem__(self, task_id: int):
        for item in reversed(self._items):
            if item[0].id == task_id:
                return item
        raise KeyError(task_id)

    def __setitem__(self, task_id: int, value):
        for i in range(len(self._items) - 1, -1, -1):
            if self._items[i][0].id == task_id:
                self._items[i] = value
                return
        self._items.append(value)
