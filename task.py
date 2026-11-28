"""
task.py — Task data model for NextUp.
"""

from datetime import date

TASK_TYPES = ("exam", "lab", "quiz", "activity", "assignment", "others")

LEGACY_TYPE_MAP = {
    "project": "lab",
    "meeting": "activity",
    "other": "others",
}


def normalize_task_type(raw_type: str) -> str:
    """Normalize task type (case-insensitive) and migrate legacy categories. O(1)."""
    clean = (raw_type or "others").strip().lower()
    clean = LEGACY_TYPE_MAP.get(clean, clean)
    return clean if clean in TASK_TYPES else "others"


class Task:
    """One academic task (assignment, quiz, project, or meeting)."""

    def __init__(self, task_id: int, name: str, subject: str,
                 deadline: date, difficulty: int,
                 estimated_hours: float = 1.0,
                 task_type: str = "others",
                 deadline_time: str = None,
                 completed: bool = False,
                 completed_at: str = None):
        self.id = task_id
        self.name = name
        self.subject = subject
        self.deadline = deadline
        self.difficulty = difficulty
        self.estimated_hours = float(estimated_hours)
        # Normalize case and migrate legacy types; unknown falls back to 'others'.
        self.task_type = normalize_task_type(task_type)
        self.deadline_time = deadline_time
        self.completed = completed
        self.completed_at = completed_at
        self.priority = 0.0  # cached by scoring.refresh_priorities()

    def deadline_str(self) -> str:
        """Return deadline as 'YYYY-MM-DD'. O(1)."""
        return self.deadline.isoformat()

    def hours_str(self) -> str:
        """Format hours cleanly (e.g., '1' instead of '1.0'). O(1)."""
        return f"{self.estimated_hours:g}"

    def to_dict(self) -> dict:
        """Serialize task to a plain dict for SQLite/JSON. O(1)."""
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "deadline": self.deadline_str(),
            "deadline_time": self.deadline_time,
            "difficulty": self.difficulty,
            "estimated_hours": self.estimated_hours,
            "task_type": self.task_type,
            "completed": self.completed,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Rebuild a Task from a stored dict. O(1)."""
        return cls(
            task_id=int(data["id"]),
            name=data["name"],
            subject=data["subject"],
            deadline=date.fromisoformat(data["deadline"]),
            difficulty=int(data["difficulty"]),
            estimated_hours=float(data.get("estimated_hours", 1.0)),
            task_type=data.get("task_type", "others"),
            deadline_time=data.get("deadline_time"),
            completed=bool(data.get("completed", False)),
            completed_at=data.get("completed_at"),
        )

    def is_overdue(self, today: date) -> bool:
        """True if incomplete and past its deadline. O(1)."""
        return (not self.completed) and self.deadline < today

    def __repr__(self) -> str:
        status = "done" if self.completed else "open"
        return (f"<Task #{self.id} '{self.name}' ({self.subject}) "
                f"due {self.deadline_str()} diff={self.difficulty} "
                f"{self.hours_str()}h {self.task_type} {status}>")
