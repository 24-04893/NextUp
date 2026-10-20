"""
scoring.py — Priority scoring engine (higher score = do first). O(1) per task.
"""

from datetime import date

# Tuning weights
URGENCY_WEIGHT = 10.0
DIFFICULTY_WEIGHT = 5.0
URGENCY_SCALE = 30.0     # max non-overdue urgency (due today = 30, floors at 0)
OVERDUE_BONUS = 1000.0   # flat bonus so overdue tasks always outrank on-time ones
HOURS_WEIGHT = 1.5       # points per estimated hour
HOURS_CAP = 8.0          # cap hours bonus so large tasks don't always dominate

TYPE_WEIGHTS = {
    "quiz": 8.0,
    "meeting": 6.0,
    "assignment": 4.0,
    "other": 2.0,
    "project": 0.0,      # size already accounted for via hours
}


def days_until(deadline: date, today: date) -> int:
    """Days until deadline (negative = overdue). O(1)."""
    return (deadline - today).days


def urgency_component(task, today: date) -> float:
    """Raw urgency points before weighting. O(1)."""
    days_left = days_until(task.deadline, today)
    if days_left < 0:
        # Flat bonus keeps all overdue tasks grouped at the top.
        return URGENCY_SCALE + OVERDUE_BONUS
    return max(0.0, URGENCY_SCALE - days_left)


def score_breakdown(task, today: date) -> dict:
    """Return individual score components and total. O(1)."""
    urgency = URGENCY_WEIGHT * urgency_component(task, today)
    difficulty = DIFFICULTY_WEIGHT * task.difficulty
    hours = HOURS_WEIGHT * min(task.estimated_hours, HOURS_CAP)
    type_pts = TYPE_WEIGHTS.get(task.task_type, 0.0)
    total = urgency + difficulty + hours + type_pts
    return {"urgency": urgency, "difficulty": difficulty,
            "hours": hours, "type": type_pts, "total": total}


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
