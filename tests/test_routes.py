"""
tests/test_routes.py
====================
Flask routes through the real test client: dashboard, add, edit,
complete, restore, validation flashes, API JSON, and the XSS check
(pasted script tags must render as TEXT, never execute).
Run: pytest tests/test_routes.py -q
"""

from datetime import timedelta

import pytest


@pytest.fixture
def env(client):
    """The client fixture yields (test_client, manager)."""
    return client


def _get(client, path):
    return client.get(path)


def test_index_renders_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Do this next" in html and "Add a task" in html


def test_add_route_then_shows_flash(client):
    today = client.get("/api/tasks").get_json()["today"]
    response = client.post("/add", data={
        "name": "Chem quiz", "subject": "Chem", "deadline": today,
        "difficulty": "3", "estimated_hours": "2", "task_type": "quiz",
    }, follow_redirects=True)
    assert "Added &#39;Chem quiz&#39;" in response.get_data(as_text=True)


def test_add_invalid_name_shows_error_flash(client):
    response = client.post("/add", data={
        "name": "   ", "subject": "CS", "deadline": "2026-11-01",
        "difficulty": "3", "estimated_hours": "1",
    }, follow_redirects=True)
    assert "cannot be empty" in response.get_data(as_text=True)


def test_add_bad_hours_shows_error_flash(client):
    response = client.post("/add", data={
        "name": "Bad hours", "subject": "CS", "deadline": "2026-11-01",
        "difficulty": "3", "estimated_hours": "0",
    }, follow_redirects=True)
    assert "greater than 0" in response.get_data(as_text=True)


def test_edit_route_updates_task(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Editable", "subject": "CS",
                              "deadline": today, "difficulty": "3"})
    task_id = client.get("/api/tasks").get_json()["tasks"][0]["id"]
    response = client.post(f"/edit/{task_id}", data={
        "name": "Editable v2", "subject": "Math", "deadline": today,
        "difficulty": "4", "estimated_hours": "3", "task_type": "quiz",
    }, follow_redirects=True)
    text = response.get_data(as_text=True)
    assert "Updated" in text and "Editable v2" in text
    edited = next(t for t in client.get("/api/tasks").get_json()["tasks"]
                  if t["id"] == task_id)
    assert edited["name"] == "Editable v2" and edited["difficulty"] == 4


def test_complete_then_restore_flow(client):
    today = client.get("/api/tasks").get_json()["today"]
    client.post("/add", data={"name": "Cycle me", "subject": "CS",
                              "deadline": today, "difficulty": "3"})
    task_id = client.get("/api/tasks").get_json()["tasks"][0]["id"]
    completed = client.post(f"/complete/{task_id}",
                            follow_redirects=True).get_data(as_text=True)
    assert "Completed" in completed
    after_done = client.get("/api/tasks").get_json()
    assert after_done["completed"] and after_done["tasks"] == []
    restored = client.post(f"/restore/{task_id}",
                           follow_redirects=True).get_data(as_text=True)
    assert "Restored" in restored
    assert client.get("/api/tasks").get_json()["tasks"]         # back open


def test_restore_unknown_id_errors(client):
    response = client.post("/restore/999", follow_redirects=True)
    assert "Nothing to restore" in response.get_data(as_text=True)


def test_complete_top_flashes_caught_up_when_empty(client):
    response = client.post("/complete-top", follow_redirects=True)
    assert "caught up" in response.get_data(as_text=True)


def test_unknown_edit_id_errors(client):
    response = client.post("/edit/1234", data={
        "name": "Ghost", "subject": "CS", "deadline": "2026-11-01",
        "difficulty": "3", "estimated_hours": "1",
    }, follow_redirects=True)
    assert "does not exist" in response.get_data(as_text=True)


def test_api_tasks_payload_shape(client):
    today = client.get("/api/tasks").get_json()["today"]
    client.post("/add", data={"name": "Shaped", "subject": "CS",
                              "deadline": today, "difficulty": "3",
                              "estimated_hours": "1.5", "task_type": "quiz"})
    data = client.get("/api/tasks").get_json()
    task = data["tasks"][0]
    for key in ("id", "name", "subject", "deadline", "difficulty",
                "estimated_hours", "task_type", "priority", "badge"):
        assert key in task
    assert task["estimated_hours"] == 1.5 and task["task_type"] == "quiz"


def test_api_top_or_null(client):
    data = client.get("/api/top").get_json()
    assert "top" in data and data["top"] is None    # empty store


def test_xss_in_task_name_is_escaped(client):
    """SECURITY: pasted <script> must appear as escaped text in the page.
    (Jinja autoescape; decorators and quotes become entities too.)"""
    today = client.get("/api/tasks").get_json()["today"]
    client.post("/add", data={
        "name": "<script>alert(1)</script>", "subject": "CS",
        "deadline": today, "difficulty": "3"})
    html = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html      # not executable HTML
    assert "&lt;script&gt;" in html                     # present as text
