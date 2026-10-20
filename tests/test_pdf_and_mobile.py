"""
tests/test_pdf_and_mobile.py — Tests for PDF export endpoints and mobile phone detection.
"""


def test_export_single_task_pdf(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]

    client.post(
        "/add",
        data={
            "name": "Lab Report — Signals & Systems",
            "subject": "ECE 301",
            "deadline": today,
            "difficulty": "4",
            "estimated_hours": "2.5",
            "task_type": "assignment",
            "deadline_time": "14:30",
        },
        follow_redirects=True,
    )

    tasks = client.get("/api/tasks").get_json()["tasks"]
    assert len(tasks) == 1
    task_id = tasks[0]["id"]

    res = client.get(f"/export/pdf/{task_id}")
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert "attachment;" in res.headers.get("Content-Disposition", "")
    assert res.data.startswith(b"%PDF-")
    assert len(res.data) > 500


def test_export_single_task_pdf_not_found(client):
    res = client.get("/export/pdf/999999")
    assert res.status_code == 404


def test_export_all_tasks_pdf(client):
    # Empty list PDF
    empty_res = client.get("/export/pdf")
    assert empty_res.status_code == 200
    assert empty_res.mimetype == "application/pdf"
    assert empty_res.data.startswith(b"%PDF-")

    # With tasks
    today = client.get("/api/tasks").get_json()["today"]
    client.post(
        "/add",
        data={
            "name": "Quiz 2 Prep",
            "subject": "CS 102",
            "deadline": today,
            "difficulty": "3",
            "estimated_hours": "1.5",
            "task_type": "quiz",
        },
        follow_redirects=True,
    )
    res = client.get("/export/pdf")
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert "nextup_tasks.pdf" in res.headers.get("Content-Disposition", "")
    assert res.data.startswith(b"%PDF-")
    assert len(res.data) > 500


def test_pdf_button_in_dashboard(client):
    today = client.get("/api/tasks").get_json()["today"]
    client.post(
        "/add",
        data={
            "name": "PDF Button Test Task",
            "subject": "CpE",
            "deadline": today,
            "difficulty": "2",
            "estimated_hours": "1",
            "task_type": "other",
        },
        follow_redirects=True,
    )

    home_html = client.get("/").get_data(as_text=True)
    assert 'href="/export/pdf"' in home_html
    assert "Export PDF (All Tasks)" in home_html
