"""
tests/test_dsa_additions.py — Tests for UndoStack, EventQueue, and DP Study Planner.
"""

from datetime import date, timedelta

from stack import UndoStack
from event_queue import EventQueue
from task import Task
from scoring import plan_study_session, refresh_priorities


def test_undo_stack_lifo_and_pop_by_id():
    st = UndoStack()
    assert st.is_empty() and st.pop() is None and st.peek() is None

    t1 = Task(1, "Task 1", "CS", date(2026, 11, 1), 2)
    t2 = Task(2, "Task 2", "CS", date(2026, 11, 2), 3)
    t3 = Task(3, "Task 3", "CS", date(2026, 11, 3), 4)

    st.push(t1, 100.0)
    st.push(t2, 200.0)
    st.push(t3, 300.0)
    assert len(st) == 3
    assert st.peek()[0] is t3

    # Pop middle item by id while preserving LIFO order of remaining items
    got = st.pop_by_id(2)
    assert got[0] is t2 and len(st) == 2
    assert st.pop()[0] is t3
    assert st.pop()[0] is t1
    assert st.is_empty()


def test_event_queue_fifo_and_bounded_capacity():
    q = EventQueue(max_size=3)
    assert q.is_empty() and q.dequeue() is None

    for i in range(5):
        q.enqueue({"op": "insert", "name": f"t{i}"})

    assert len(q) == 3
    names = [e["name"] for e in q]
    assert names == ["t2", "t3", "t4"]
    assert q.dequeue()["name"] == "t2"
    assert len(q) == 2


def test_dp_plan_study_session_optimal_subset():
    today = date(2026, 11, 1)
    # Task A: 3h, lower score; Tasks B + C: 2h + 2h = 4h, higher combined score
    t_a = Task(1, "Long Low", "CS", today + timedelta(days=10), 1, estimated_hours=3.0)
    t_b = Task(2, "Quick High 1", "CS", today, 5, estimated_hours=2.0)
    t_c = Task(3, "Quick High 2", "CS", today + timedelta(days=1), 4, estimated_hours=2.0)
    tasks = refresh_priorities([t_a, t_b, t_c], today)

    plan = plan_study_session(tasks, 4.0)
    picked_ids = {t.id for t in plan["selected"]}
    assert picked_ids == {2, 3}
    assert plan["used_hours"] == 4.0
    assert plan["total_score"] == round(t_b.priority + t_c.priority, 1)


def test_api_plan_session_route(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "DP Quiz", "subject": "CS",
                              "deadline": today, "difficulty": "4",
                              "estimated_hours": "1.5", "task_type": "quiz"},
                follow_redirects=True)
    client.post("/add", data={"name": "DP Project", "subject": "CS",
                              "deadline": today, "difficulty": "5",
                              "estimated_hours": "5.0", "task_type": "project"},
                follow_redirects=True)

    res = client.post("/api/plan-session", json={"hours": 2.0})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["used_hours"] == 1.5
    assert [t["name"] for t in data["tasks"]] == ["DP Quiz"]

    bad = client.post("/api/plan-session", json={"hours": 0})
    assert bad.status_code == 400
