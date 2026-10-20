"""
event_queue.py — Hand-built bounded FIFO Queue backed by a singly-linked list.
"""


class _QNode:
    """Linked-list node for EventQueue."""

    __slots__ = ("value", "next")

    def __init__(self, value):
        self.value = value
        self.next = None


class EventQueue:
    """Bounded FIFO queue (max_size=20) with O(1) enqueue and dequeue."""

    def __init__(self, max_size: int = 20):
        self._head = None
        self._tail = None
        self._size = 0
        self._max_size = max_size

    def is_empty(self) -> bool:
        """True when no events are queued. O(1)."""
        return self._size == 0

    def __len__(self) -> int:
        return self._size

    def enqueue(self, value) -> None:
        """Add event to the tail; dequeue oldest if full. O(1)."""
        node = _QNode(value)
        if self._tail is None:
            self._head = self._tail = node
        else:
            self._tail.next = node
            self._tail = node
        self._size += 1
        if self._size > self._max_size:
            self.dequeue()

    def dequeue(self):
        """Remove and return the oldest event from the head, or None. O(1)."""
        if self._head is None:
            return None
        val = self._head.value
        self._head = self._head.next
        if self._head is None:
            self._tail = None
        self._size -= 1
        return val

    def append(self, value) -> None:
        """Alias for enqueue() for list-compatible callers. O(1)."""
        self.enqueue(value)

    def __iter__(self):
        cur = self._head
        while cur is not None:
            yield cur.value
            cur = cur.next

    def __reversed__(self):
        return reversed(list(self))

    def __getitem__(self, idx):
        return list(self)[idx]
