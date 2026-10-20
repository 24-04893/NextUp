"""
tests/test_scoring.py
=====================
The four-component score: urgency + difficulty + hours + type.
25+ test goal (part of). Run: pytest tests/test_scoring.py -q
"""

import pytest                      # gives `pytest.raises` etc. (fixture only)

from datetime import date, timedelta
from task import Task
from scoring import (priority_score, score_breakdown, refresh_priorities,
                     URGENCY_SCALE, OVERDUE_BONUS, HOURS_CAP,
                     TYPE_WEIGHTS)

TODAY = date(2026, 10, 20)         # pinned, so numbers never drift


def _make(days, diff=3, hours=1.0, kind="other"):
    """Shortcut Task builder (ids unique per call via a counter)."""
    _make.n = getattr(_make, "n", 0) + 1
    return Task(_make.n, f"t{_make.n}", "CS",
                TODAY + timedelta(days=days), diff,
                estimated_hours=hours, task_type=kind)


# 1. Every component lands in the breakdown dict, and they ADD UP to the total.
def test_breakdown_components_sum_to_total():
    bd = score_breakdown(_make(days=5, diff=4, hours=2.0, kind="quiz"), TODAY)
    assert set(bd) == {"urgency", "difficulty", "hours", "type", "total"}
    assert pytest.approx(bd["total"]) == (
        bd["urgency"] + bd["difficulty"] + bd["hours"] + bd["type"])
    # and the total is what the task carries as its cached priority
    t = _make(days=5)
    t.priority = priority_score(t, TODAY)
    assert t.priority == score_breakdown(t, TODAY)["total"]


# 2. Urgency arithmetic: exactly URGENCY_SCALE points for today, -10 per day.
def test_urgency_component_values():
    bd_today = score_breakdown(_make(0), TODAY)
    assert bd_today["urgency"] == URGENCY_SCALE * 10.0
    bd_later = score_breakdown(_make(5), TODAY)
    assert bd_later["urgency"] == (URGENCY_SCALE - 5) * 10.0


# 3. Overdue beats EVERYTHING on time -- the flat OVERDUE_BONUS rule.
def test_overdue_beats_everything():
    overdue = priority_score(_make(-1), TODAY)
    best_ontime = priority_score(
        _make(0, diff=5, hours=HOURS_CAP, kind="quiz"), TODAY)
    assert overdue > best_ontime
    # and lateness does NOT keep growing: -1 day and -40 day match
    assert priority_score(_make(-1), TODAY) == priority_score(_make(-40), TODAY)
    assert URGENCY_SCALE + OVERDUE_BONUS > 40.0 * 10.0   # un-reachievable


# 4. Hours earn points but STOP at the cap: 8h == 12h == 20h of score.
def test_hours_component_is_capped():
    eight = score_breakdown(_make(3, hours=8.0), TODAY)["hours"]
    twelve = score_breakdown(_make(3, hours=12.0), TODAY)["hours"]
    twenty = score_breakdown(_make(3, hours=20.0), TODAY)["hours"]
    onetb = score_breakdown(_make(3, hours=1.0), TODAY)["hours"]
    assert eight == twelve == twenty, "cap must flatten everything above 8h"
    assert onetb < eight              # yet small work still scores less


# 5. The spec's headline: a MEETING today outranks a PROJECT due in 2 weeks.
def test_meeting_today_beats_project_two_weeks():
    meeting_today = priority_score(_make(0, diff=2, kind="meeting"), TODAY)
    project_later = priority_score(_make(14, diff=5, kind="project"), TODAY)
    assert meeting_today > project_later


# 6. Same day, same everything: quiz > assignment > project (type order).
def test_type_weight_ordering():
    quiz = priority_score(_make(3, kind="quiz"), TODAY)
    assignment = priority_score(_make(3, kind="assignment"), TODAY)
    project = priority_score(_make(3, kind="project"), TODAY)
    assert quiz > assignment > project
    assert set(TYPE_WEIGHTS) == {"quiz", "meeting", "assignment",
                                 "other", "project"}


# 7. refresh_priorities(): re-scores AND sorts highest-first, ties to deadline.
def test_refresh_priorities_orders_and_rescores():
    tasks = [_make(10), _make(1), _make(3)]
    for t in tasks:
        t.priority = 0.0                       # wipe; refresh must refill
    ranked = refresh_priorities(tasks, TODAY)
    assert [t.deadline for t in ranked] == \
        sorted(t.deadline for t in ranked)     # ties fall to earlier deadline
    assert all(t.priority > 0 for t in ranked)
