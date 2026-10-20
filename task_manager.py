"""
task_manager.py — Coordinates Task dict, MaxHeap, AVLTree, and SQLite storage.

Sync guarantees:
  1. Single entry point: every mutation updates heap, AVL, and SQLite together.
  2. Rebuild on load: prepare_dashboard() re-scores and rebuilds both structures.
"""

import os
import tempfile
import time
from datetime import date

from task import TASK_TYPES, Task
from heap import MaxHeap
from avl_tree import AVLTree
from stack import UndoStack
from scoring import refresh_priorities, priority_score
from storage import TaskStore

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5
MAX_NAME_LEN = 80
MAX_SUBJECT_LEN = 40
MAX_HOURS = 24.0


class TaskManager:
    """Owns all tasks and keeps MaxHeap, AVLTree, and SQLite in sync."""

    def __init__(self, db_path=None, legacy_json=None):
        if db_path is None:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            if os.environ.get("VERCEL") or not os.access(app_dir, os.W_OK):
                db_path = os.path.join(tempfile.gettempdir(), "nextup.db")
            else:
                db_path = os.path.join(app_dir, "nextup.db")
        self.store = TaskStore(db_path)
        if self.store._fresh:
            if legacy_json is None:
                legacy_json = os.environ.get(
                    "NEXTUP_LEGACY_JSON",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "tasks.json"))
            self.store.migrate_from_json(legacy_json)
        self._tasks = {}         # id -> Task (all tasks)
        self._trash = UndoStack()  # LIFO stack of (Task, expiry_epoch) for undo window
        self._heap = MaxHeap()   # open tasks ordered by priority
        self._avl = AVLTree()    # open tasks ordered by (deadline, id)
        self._next_id = self.store.next_id()
        self._load()

    def today(self) -> date:
        """Return current date (wrapped for test overrides). O(1)."""
        return date.today()

    def _open_tasks(self):
        """Return all incomplete tasks. O(n)."""
        return [t for t in self._tasks.values() if not t.completed]

    def _insert_open(self, task, priority):
        """Insert an open task into both heap and AVL. O(log n)."""
        self._heap.insert(task, priority)
        self._avl.insert(task)

    def _retire(self, task):
        """Mark task completed and remove it from both heap and AVL. O(log n)."""
        task.completed = True
        self._heap.remove(task.id)
        self._avl.delete(task)

    @staticmethod
    def validate_name(name):
        """Validate non-empty, length-capped task name. O(1)."""
        if not name or not str(name).strip():
            raise ValueError("Task name cannot be empty.")
        clean = str(name).strip()
        if len(clean) > MAX_NAME_LEN:
            raise ValueError(f"Task name is too long (max {MAX_NAME_LEN} characters).")
        return clean

    @staticmethod
    def validate_difficulty(value):
        """Validate integer difficulty in 1..5. O(1)."""
        try:
            diff = int(value)
        except (TypeError, ValueError):
            raise ValueError("Difficulty must be a number 1-5.")
        if not (MIN_DIFFICULTY <= diff <= MAX_DIFFICULTY):
            raise ValueError("Difficulty must be between 1 and 5.")
        return diff

    @staticmethod
    def parse_deadline(text):
        """Parse 'YYYY-MM-DD' into datetime.date. O(1)."""
        if not text:
            raise ValueError("Deadline is required.")
        try:
            return date.fromisoformat(str(text).strip())
        except ValueError:
            raise ValueError("Deadline must be a valid date (YYYY-MM-DD).")

    @staticmethod
    def validate_hours(value):
        """Validate estimated hours (0 < hours <= 24). O(1)."""
        try:
            hours = float(value)
        except (TypeError, ValueError):
            raise ValueError("Estimated hours must be a number.")
        if hours <= 0:
            raise ValueError("Estimated hours must be greater than 0.")
        if hours > MAX_HOURS:
            raise ValueError(f"Estimated hours can be at most {MAX_HOURS:g}.")
        return hours

    @staticmethod
    def validate_type(task_type):
        """Validate task type against TASK_TYPES (defaults to 'other'). O(1)."""
        clean = (task_type or "other").strip().lower()
        if clean not in TASK_TYPES:
            valid = ", ".join(TASK_TYPES)
            raise ValueError(f"Task type must be one of: {valid}.")
        return clean

    @staticmethod
    def validate_time(text):
        """Validate optional 'HH:MM' meeting time. O(1)."""
        if text is None or str(text).strip() == "":
            return None
        raw = str(text).strip()
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValueError("Meeting time must look like HH:MM.")
        try:
            hh, mm = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError("Meeting time must look like HH:MM.")
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("Meeting time must be a valid HH:MM within 00:00..23:59.")
        return f"{hh:02d}:{mm:02d}"

    @classmethod
    def parse_form(cls, form):
        """Validate all task fields from a form mapping. O(1)."""
        return {
            "name": cls.validate_name(form.get("name", "")),
            "subject": (form.get("subject") or "").strip()[:MAX_SUBJECT_LEN],
            "deadline": cls.parse_deadline(form.get("deadline", "")),
            "difficulty": cls.validate_difficulty(form.get("difficulty", "")),
            "estimated_hours": cls.validate_hours(
                form.get("estimated_hours", 1)),
            "task_type": cls.validate_type(form.get("task_type", "other")),
            "deadline_time": cls.validate_time(form.get("deadline_time")),
        }

    def add_task(self, name, subject, deadline_text, difficulty,
                 estimated_hours=1.0, task_type="other", deadline_time=None):
        """Validate, store, and index a new task; returns (task, warnings). O(log n)."""
        name = self.validate_name(name)
        subject = (subject or "").strip()[:MAX_SUBJECT_LEN]
        deadline = self.parse_deadline(deadline_text)
        difficulty = self.validate_difficulty(difficulty)
        estimated_hours = self.validate_hours(estimated_hours)
        task_type = self.validate_type(task_type)
        deadline_time = self.validate_time(deadline_time)

        warnings = []
        if deadline < self.today():
            warnings.append("Heads-up: this date is in the past "
                            "(the task starts out OVERDUE).")

        task = Task(self._next_id, name, subject, deadline, difficulty,
                    estimated_hours=estimated_hours, task_type=task_type,
                    deadline_time=deadline_time)
        self._next_id += 1

        self._tasks[task.id] = task
        self._insert_open(task, priority_score(task, self.today()))
        self.store.upsert(task)
        return task, warnings

    def edit_task(self, task_id, name, subject, deadline_text, difficulty,
                  estimated_hours, task_type, deadline_time=None):
        """Validate and update an open task, keeping heap and AVL in sync. O(log n)."""
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError("That task does not exist.")
        if task.completed:
            raise ValueError("Completed tasks cannot be edited (restore it first).")

        fields = self.parse_form({"name": name, "subject": subject,
                                  "deadline": deadline_text,
                                  "difficulty": difficulty,
                                  "estimated_hours": estimated_hours,
                                  "task_type": task_type,
                                  "deadline_time": deadline_time})

        warnings = []
        if fields["deadline"] < self.today() and fields["deadline"] != task.deadline:
            warnings.append("Heads-up: this date is in the past "
                            "(the task becomes OVERDUE).")

        deadline_moved = fields["deadline"] != task.deadline

        # Delete old AVL key before overwriting task.deadline.
        if deadline_moved:
            self._avl.delete(task)

        task.name = fields["name"]
        task.subject = fields["subject"]
        task.difficulty = fields["difficulty"]
        task.estimated_hours = fields["estimated_hours"]
        task.task_type = fields["task_type"]
        task.deadline_time = fields["deadline_time"]
        task.deadline = fields["deadline"]

        new_score = priority_score(task, self.today())
        self._heap.update_priority(task.id, new_score)
        if deadline_moved:
            self._avl.insert(task)
        task.priority = new_score

        self.store.upsert(task)
        return task, warnings

    def complete_task(self, task_id):
        """Mark task completed and remove from heap and AVL. O(log n)."""
        task = self._tasks.get(task_id)
        if task is None or task.completed:
            return None
        self._retire(task)
        from datetime import datetime as _dt
        task.completed_at = _dt.now().isoformat(timespec="seconds")
        self.store.upsert(task)
        return task

    def complete_top(self):
        """Pop highest-priority task from heap and remove from AVL. O(log n)."""
        task = self._heap.extract_max()
        if task is None:
            return None
        task.completed = True
        self._avl.delete(task)
        from datetime import datetime as _dt
        task.completed_at = _dt.now().isoformat(timespec="seconds")
        self.store.upsert(task)
        return task

    UNDO_WINDOW_S = 6.5

    def delete_task(self, task_id, keep_undo=True):
        """Hard-delete a task from dict, heap, AVL, and SQLite (with 6.5s undo stack). O(log n)."""
        task = self._tasks.pop(task_id, None)
        if task is None:
            return None
        self._heap.remove(task.id)
        self._avl.delete(task)
        self.store.delete(task.id)
        if keep_undo:
            self._trash.push(task, time.time() + self.UNDO_WINDOW_S)
        return task

    def undelete_task(self, task_id):
        """Pop a hard-deleted task from the undo stack if still within the undo window."""
        entry = self._trash.pop_by_id(task_id)
        if entry is None:
            return None
        task, expiry = entry
        if time.time() > expiry:
            return None
        self._tasks[task.id] = task
        self.store.upsert(task)
        if not task.completed:
            self._insert_open(task, priority_score(task, self.today()))
        return task

    def restore_task(self, task_id):
        """Re-open a completed task and re-insert into heap and AVL. O(log n)."""
        task = self._tasks.get(task_id)
        if task is None or not task.completed:
            return None
        task.completed = False
        task.completed_at = None
        self._insert_open(task, priority_score(task, self.today()))
        self.store.upsert(task)
        return task

    def _record_rebuild(self, count):
        """Enqueue a single rebuild event into the AVL event queue. O(1)."""
        self._avl.log.enqueue({"op": "rebuild", "name": f"{count} tasks"})

    def structures_page(self):
        """Return AVL JSON, heap JSON, and recent event log for /structures. O(n)."""
        self.prepare_dashboard()
        return {"avl": self._avl.export_json(),
                "heap": self._heap.export_json(),
                "log": list(reversed(self._avl.log))}

    def prepare_dashboard(self, today=None):
        """Re-score open tasks, rebuild heap (O(n)) and AVL (O(n log n)), and return views."""
        if today is None:
            today = self.today()
        open_tasks = self._open_tasks()
        by_priority = refresh_priorities(open_tasks, today)

        self._heap.build([MaxHeap.make_key(t, t.priority) for t in open_tasks])

        # Preserve rotation history across rebuilds by muting individual inserts.
        stash = self._avl.log
        self._avl = AVLTree()
        self._avl.log = stash
        self._avl.mute = True
        for t in open_tasks:
            self._avl.insert(t)
        self._avl.mute = False
        if open_tasks:
            self._record_rebuild(len(open_tasks))

        top = self._heap.peek()
        sorted_list = self._avl.inorder()
        completed = sorted([t for t in self._tasks.values() if t.completed],
                           key=lambda t: (t.completed_at or "", t.id),
                           reverse=True)
        return {"top": top, "by_priority": by_priority,
                "sorted_list": sorted_list, "completed": completed,
                "today": today}

    def filter_dashboard(self, subject=None, query=None,
                         start=None, end=None):
        """Apply subject, text query, and AVL range_query filters to dashboard views."""
        dash = self.prepare_dashboard()
        q = (query or "").strip().lower()

        def keeps(t):
            return (((subject is None) or (t.subject == subject))
                    and (not q or (q in t.name.lower()))
                    and ((start is None) or (t.deadline >= start))
                    and ((end is None) or (t.deadline <= end)))

        if start is not None and end is not None:
            date_hits = self._avl.range_query(start, end)
            range_stats = (self._avl.visited, self._avl.node_count())
            sorted_list = [t for t in date_hits if keeps(t)]
        else:
            range_stats = (0, self._avl.node_count())
            sorted_list = [t for t in dash["sorted_list"] if keeps(t)]

        by_priority = [t for t in dash["by_priority"] if keeps(t)]

        counts = {}
        for t in self._open_tasks():
            if t.subject:
                counts[t.subject] = counts.get(t.subject, 0) + 1
        ordered = sorted(counts, key=lambda s: (-counts[s], s))

        return {"top": dash["top"], "by_priority": by_priority,
                "sorted_list": sorted_list, "completed": dash["completed"],
                "subjects": [(s, counts[s]) for s in ordered],
                "today": dash["today"], "range_stats": range_stats,
                "query": query or "", "subject": subject or ""}

    def _load(self):
        """Load persisted tasks from SQLite into self._tasks. O(n)."""
        for entry in self.store.load_tasks():
            try:
                task = Task.from_dict(entry)
            except (KeyError, ValueError) as exc:
                print(f"[NextUp] skipping a bad task row: {exc}")
                continue
            self._tasks[task.id] = task
        self._next_id = self.store.next_id()
        print(f"[NextUp] loaded {len(self._tasks)} task(s) "
              f"from {os.path.basename(self.store.db_path)}")

    def status(self):
        """Return total, open, and completed task counts. O(n)."""
        return {"total": len(self._tasks),
                "open": len(self._open_tasks()),
                "completed": sum(1 for t in self._tasks.values() if t.completed)}
