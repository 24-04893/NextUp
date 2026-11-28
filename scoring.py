"""
scoring.py — Weighted Sum Model (WSM) priority scoring engine (higher score = do first). O(1) per task.
"""

import math
from datetime import date, datetime, time as dt_time

# AHP / ROC criteria weights (must sum to 1.0)
W_URGENCY = 0.45
W_TYPE = 0.25
W_DIFFICULTY = 0.15
W_SIZE = 0.15

# Normalization parameters (0-100 scale; urgency is non-saturating for overdue tasks)
URGENCY_SCALE = 100.0
URGENCY_DECAY_K = 0.30
DIFFICULTY_MAX = 5.0
HOURS_CAP = 8.0                    # cap hours so large tasks don't dominate
DEFAULT_DEADLINE_TIME = dt_time(23, 59)

TYPE_WEIGHTS = {
    "exam": 95.0,
    "lab": 85.0,
    "quiz": 80.0,
    "activity": 70.0,
    "assignment": 65.0,
    "others": 45.0,
}

_LEGACY_TYPE_ALIASES = {
    "project": "lab",
    "meeting": "activity",
    "other": "others",
}


def type_score(task_type: str) -> float:
    """Map task type (case-insensitive) to normalized 0-100 rubric score. O(1)."""
    clean = (task_type or "others").strip().lower()
    clean = _LEGACY_TYPE_ALIASES.get(clean, clean)
    return TYPE_WEIGHTS.get(clean, TYPE_WEIGHTS["others"])


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _deadline_datetime(task) -> datetime:
    """Combine task.deadline and optional task.deadline_time (default 23:59) into a datetime. O(1)."""
    raw_time = getattr(task, "deadline_time", None)
    due_time = DEFAULT_DEADLINE_TIME
    if raw_time:
        try:
            hh, mm = str(raw_time).strip().split(":")
            due_time = dt_time(int(hh), int(mm))
        except (ValueError, TypeError):
            due_time = DEFAULT_DEADLINE_TIME
    return datetime.combine(task.deadline, due_time)


def _current_datetime(today) -> datetime:
    """Resolve `today` (date or datetime) into current datetime. O(1)."""
    if isinstance(today, datetime):
        return today
    if today == date.today():
        return datetime.now()
    return datetime.combine(today, dt_time(0, 0))


def days_until(deadline, today, deadline_time: str = None) -> float:
    """Exact days remaining until deadline (negative = overdue). O(1)."""
    if isinstance(deadline, datetime):
        deadline_dt = deadline
    else:
        due_time = DEFAULT_DEADLINE_TIME
        if deadline_time:
            try:
                hh, mm = str(deadline_time).strip().split(":")
                due_time = dt_time(int(hh), int(mm))
            except (ValueError, TypeError):
                due_time = DEFAULT_DEADLINE_TIME
        deadline_dt = datetime.combine(deadline, due_time)
    current_dt = _current_datetime(today)
    return (deadline_dt - current_dt).total_seconds() / 86400.0


def urgency_component(task, today) -> float:
    """Normalized urgency score via continuous exponential decay: 100 * e^(-k * days_left). O(1)."""
    days_left = (_deadline_datetime(task) - _current_datetime(today)).total_seconds() / 86400.0
    return URGENCY_SCALE * math.exp(-URGENCY_DECAY_K * days_left)


def score_breakdown(task, today) -> dict:
    """Return weighted score components, normalized (0-100) values, weights, and total. O(1)."""
    days_left = (_deadline_datetime(task) - _current_datetime(today)).total_seconds() / 86400.0
    u_norm = URGENCY_SCALE * math.exp(-URGENCY_DECAY_K * days_left)
    t_norm = type_score(task.task_type)
    d_norm = _clamp(100.0 * (task.difficulty / DIFFICULTY_MAX))
    s_norm = _clamp(100.0 * (task.estimated_hours / HOURS_CAP))

    urgency = W_URGENCY * u_norm
    type_pts = W_TYPE * t_norm
    difficulty = W_DIFFICULTY * d_norm
    hours = W_SIZE * s_norm
    total = urgency + type_pts + difficulty + hours

    return {
        "urgency": urgency,
        "difficulty": difficulty,
        "hours": hours,
        "type": type_pts,
        "total": total,
        "days_left": days_left,
        "normalized": {
            "urgency": u_norm,
            "type": t_norm,
            "difficulty": d_norm,
            "hours": s_norm,
        },
        "weights": {
            "urgency": W_URGENCY,
            "type": W_TYPE,
            "difficulty": W_DIFFICULTY,
            "hours": W_SIZE,
        },
    }


def priority_score(task, today: date) -> float:
    """Compute total priority score (higher = do first). O(1)."""
    return score_breakdown(task, today)["total"]


def refresh_priorities(tasks, today: date):
    """Re-score all tasks against today and return sorted list (score desc, deadline asc). O(n log n)."""
    for task in tasks:
        task.priority = priority_score(task, today)
    return sorted(tasks, key=lambda t: (-t.priority, t.deadline, t.id))


def plan_study_session(tasks, available_hours: float) -> dict:
    """0/1 Knapsack Dynamic Programming: pick open tasks maximizing total priority within available_hours. O(n * W)."""
    if available_hours <= 0 or not tasks:
        return {"selected": [], "used_hours": 0.0, "total_score": 0.0}

    # Discretize hours into 0.5h units so DP table handles fractional estimates cleanly.
    cap = min(48, max(0, int(round(available_hours * 2))))
    if cap == 0:
        return {"selected": [], "used_hours": 0.0, "total_score": 0.0}

    n = len(tasks)
    weights = [max(1, int(round(t.estimated_hours * 2))) for t in tasks]
    values = [t.priority for t in tasks]

    dp = [[0.0] * (cap + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        w, v = weights[i - 1], values[i - 1]
        for c in range(cap + 1):
            dp[i][c] = dp[i - 1][c]
            if w <= c and dp[i - 1][c - w] + v > dp[i][c]:
                dp[i][c] = dp[i - 1][c - w] + v

    # Backtrack to recover chosen tasks.
    selected = []
    c = cap
    for i in range(n, 0, -1):
        if dp[i][c] != dp[i - 1][c]:
            selected.append(tasks[i - 1])
            c -= weights[i - 1]
    selected.sort(key=lambda t: (-t.priority, t.deadline, t.id))

    return {
        "selected": selected,
        "used_hours": round(sum(t.estimated_hours for t in selected), 1),
        "total_score": round(sum(t.priority for t in selected), 1),
    }
