"""
tests/test_scoring.py
=====================
The four-component Weighted Sum Model (WSM): urgency + type + difficulty + size.
Run: pytest tests/test_scoring.py -q
"""

import math
import pytest

from datetime import date, datetime, timedelta
from task import Task
from scoring import (
    priority_score, score_breakdown, refresh_priorities, days_until, type_score,
    W_URGENCY, W_TYPE, W_DIFFICULTY, W_SIZE,
    URGENCY_SCALE, URGENCY_DECAY_K, DIFFICULTY_MAX, HOURS_CAP, TYPE_WEIGHTS,
)

TODAY = date(2026, 10, 20)         # pinned, so numbers never drift (00:00)
NOW = datetime(2026, 10, 20, 12, 0)


def _make(days, diff=3, hours=1.0, kind="other", deadline_time=None):
    """Shortcut Task builder (ids unique per call via a counter)."""
    _make.n = getattr(_make, "n", 0) + 1
    return Task(_make.n, f"t{_make.n}", "CS",
                TODAY + timedelta(days=days), diff,
                estimated_hours=hours, task_type=kind,
                deadline_time=deadline_time)


# 1. Weights sum to 1.0 and breakdown components ADD UP to the total.
def test_breakdown_components_sum_to_total():
    assert pytest.approx(1.0) == W_URGENCY + W_TYPE + W_DIFFICULTY + W_SIZE
    assert URGENCY_DECAY_K == 0.30
    bd = score_breakdown(_make(days=5, diff=4, hours=2.0, kind="quiz"), TODAY)
    assert {"urgency", "difficulty", "hours", "type", "total", "days_left", "normalized", "weights"} <= set(bd)
    assert pytest.approx(bd["total"]) == (
        bd["urgency"] + bd["difficulty"] + bd["hours"] + bd["type"])
    t = _make(days=5)
    t.priority = priority_score(t, TODAY)
    assert t.priority == score_breakdown(t, TODAY)["total"]


# 2. Urgency arithmetic: continuous exponential decay U = 100 * e^(-0.30 * days_left) with exact timestamps.
def test_urgency_component_values():
    bd_exact = score_breakdown(_make(0, deadline_time="12:00"), NOW)
    assert pytest.approx(bd_exact["days_left"]) == 0.0
    assert pytest.approx(bd_exact["normalized"]["urgency"]) == URGENCY_SCALE
    assert pytest.approx(bd_exact["urgency"]) == W_URGENCY * URGENCY_SCALE

    bd_default_time = score_breakdown(_make(0), NOW)
    expected_dl = (datetime(2026, 10, 20, 23, 59) - NOW).total_seconds() / 86400.0
    assert pytest.approx(bd_default_time["days_left"]) == expected_dl
    expected_u = URGENCY_SCALE * math.exp(-URGENCY_DECAY_K * expected_dl)
    assert pytest.approx(bd_default_time["normalized"]["urgency"]) == expected_u

    bd_later = score_breakdown(_make(5), TODAY)
    dl_later = days_until(TODAY + timedelta(days=5), TODAY)
    expected_later = URGENCY_SCALE * math.exp(-URGENCY_DECAY_K * dl_later)
    assert pytest.approx(bd_later["normalized"]["urgency"]) == expected_later
    assert pytest.approx(bd_later["urgency"]) == W_URGENCY * expected_later


# 3. Non-saturating overdue urgency: overdue beats on-time & more-overdue scores higher.
def test_overdue_is_non_saturating():
    overdue_1 = priority_score(_make(-1), NOW)
    overdue_5 = priority_score(_make(-5), NOW)
    overdue_40 = priority_score(_make(-40), NOW)
    due_today = priority_score(_make(0), NOW)
    assert overdue_40 > overdue_5 > overdue_1 > due_today


# 4. Brutal due-today project beats future tasks.
def test_brutal_due_today_project_beats_future_task():
    brutal_project = priority_score(_make(0, diff=5, hours=8.0, kind="project"), NOW)
    future_quiz = priority_score(_make(4, diff=3, hours=2.0, kind="quiz"), NOW)
    assert brutal_project > future_quiz


# 5. Hours earn points up to the 8h cap: 8h == 12h == 20h, and 2.5h -> 31.25 normalized.
def test_hours_component_is_capped():
    two_half = score_breakdown(_make(3, hours=2.5), TODAY)
    assert pytest.approx(two_half["normalized"]["hours"]) == 31.25
    assert round(two_half["hours"], 2) == 4.69

    eight = score_breakdown(_make(3, hours=8.0), TODAY)["hours"]
    twelve = score_breakdown(_make(3, hours=12.0), TODAY)["hours"]
    twenty = score_breakdown(_make(3, hours=20.0), TODAY)["hours"]
    onetb = score_breakdown(_make(3, hours=1.0), TODAY)["hours"]
    assert eight == twelve == twenty, "cap must flatten everything above 8h"
    assert onetb < eight              # yet small work still scores less


# 6. A MEETING today outranks a PROJECT due in 2 weeks.
def test_meeting_today_beats_project_two_weeks():
    meeting_today = priority_score(_make(0, diff=2, kind="meeting"), TODAY)
    project_later = priority_score(_make(14, diff=5, kind="project"), TODAY)
    assert meeting_today > project_later


# 7. Same day, same everything: exam > lab > quiz > activity > assignment > others (case-insensitive).
def test_type_weight_ordering():
    exam = priority_score(_make(3, kind="exam"), TODAY)
    lab = priority_score(_make(3, kind="lab"), TODAY)
    quiz = priority_score(_make(3, kind="quiz"), TODAY)
    activity = priority_score(_make(3, kind="activity"), TODAY)
    assignment = priority_score(_make(3, kind="assignment"), TODAY)
    others = priority_score(_make(3, kind="others"), TODAY)
    assert exam > lab > quiz > activity > assignment > others
    assert set(TYPE_WEIGHTS) == {"exam", "lab", "quiz", "activity", "assignment", "others"}
    assert type_score("EXAM") == 95.0
    assert type_score("Lab") == 85.0
    assert type_score("project") == 85.0
    assert type_score("others") == 45.0


# 8. Difficulty normalizes 1..5 onto 0..100.
def test_difficulty_normalization():
    bd_max = score_breakdown(_make(3, diff=int(DIFFICULTY_MAX)), TODAY)
    assert pytest.approx(bd_max["normalized"]["difficulty"]) == 100.0
    assert pytest.approx(bd_max["difficulty"]) == W_DIFFICULTY * 100.0


# 9. refresh_priorities(): re-scores AND sorts highest-first, ties to deadline.
def test_refresh_priorities_orders_and_rescores():
    tasks = [_make(10), _make(1), _make(3)]
    for t in tasks:
        t.priority = 0.0                       # wipe; refresh must refill
    ranked = refresh_priorities(tasks, TODAY)
    assert [t.deadline for t in ranked] == \
        sorted(t.deadline for t in ranked)     # ties fall to earlier deadline
    assert all(t.priority > 0 for t in ranked)
