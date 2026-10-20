"""
tests/test_multiuser_auth.py
============================
Verify per-student account persistence and isolated task storage.
"""

from datetime import date, timedelta


def test_two_students_have_isolated_tasks_and_persisted_login(client):
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # 1. Student A signs up and adds a task
    r1 = client.post("/auth/signup", json={
        "name": "Alice Santos",
        "program": "BS CpE",
        "yearLevel": "3rd Year",
        "password": "secret-alice",
    })
    assert r1.status_code == 200
    assert r1.get_json()["user"]["name"] == "Alice Santos"

    client.post("/add", data={
        "name": "Alice Capstone",
        "subject": "CpE 3102",
        "deadline": today,
        "difficulty": "4",
        "estimated_hours": "2",
        "task_type": "project",
    })
    alice_tasks = [t["name"] for t in client.get("/api/tasks").get_json()["tasks"]]
    assert alice_tasks == ["Alice Capstone"]

    # 2. Alice logs out; Student B signs up and sees 0 tasks
    client.post("/auth/logout")
    r2 = client.post("/auth/signup", json={
        "name": "Bob Reyes",
        "program": "BS CS",
        "yearLevel": "2nd Year",
        "password": "secret-bob",
    })
    assert r2.status_code == 200
    bob_tasks_initial = client.get("/api/tasks").get_json()["tasks"]
    assert bob_tasks_initial == []

    client.post("/add", data={
        "name": "Bob Algorithm Lab",
        "subject": "CS 201",
        "deadline": tomorrow,
        "difficulty": "3",
        "estimated_hours": "1.5",
        "task_type": "assignment",
    })
    bob_tasks = [t["name"] for t in client.get("/api/tasks").get_json()["tasks"]]
    assert bob_tasks == ["Bob Algorithm Lab"]

    # 3. Bob logs out; wrong password for Alice fails
    client.post("/auth/logout")
    bad = client.post("/auth/login", json={"name": "Alice Santos", "password": "wrong"})
    assert bad.status_code == 401

    # 4. Alice logs back in and sees only her own task
    good = client.post("/auth/login", json={"name": "alice santos", "password": "secret-alice"})
    assert good.status_code == 200
    alice_again = [t["name"] for t in client.get("/api/tasks").get_json()["tasks"]]
    assert alice_again == ["Alice Capstone"]


def test_demo_mode_preloads_eight_subjects_across_seven_days(client):
    res = client.post("/auth/demo")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["user"]["name"] == "Demo Student"

    tasks_resp = client.get("/api/tasks").get_json()
    tasks = tasks_resp["tasks"]
    assert len(tasks) == 8

    expected_subjects = {
        "CpE 411", "CpE 414", "Fili 102", "CpE 413",
        "CpE 415", "CpE 412", "CpE 410", "ENGG 416",
    }
    assert {t["subject"] for t in tasks} == expected_subjects

    today = date.fromisoformat(tasks_resp["today"])
    for t in tasks:
        d = date.fromisoformat(t["deadline"])
        assert 0 <= (d - today).days <= 6
        assert 1 <= t["difficulty"] <= 5
        assert t["deadline_time"]

    # Logging out clears demo mode
    client.post("/auth/logout")
    me = client.get("/auth/me").get_json()
    assert me["user"] is None
