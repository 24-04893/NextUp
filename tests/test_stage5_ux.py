"""
tests/test_stage5_ux.py
=======================
STAGE 5: dark mode is CSS-only (no tests), but these hold:
  * /export.ics -- valid RFC 5545 skeleton: CRLF line endings, UID,
    DTSTART date VALUE, SUMMARY/DESCRIPTION contents, ,;\\ escaping,
    75-octet folding with single-space continuations,
  * the 'Export to calendar' button,
  * the 7-day strip: one link per day with its OWN from/to, count +
    hours, day click filters via the existing range machinery.
Run: pytest tests/test_stage5_ux.py -q
"""

import re

from datetime import timedelta


# ----------------------------------------------------------------------
# /export.ics
# ----------------------------------------------------------------------
def _fixed(hhmm):
    return hhmm


def test_ics_route_headers(client):
    resp = client.get("/export.ics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/calendar"
    body = resp.get_data(as_text=True)
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert body.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in body
    assert "PRODID:" in body


def test_ics_one_vevent_per_open_task(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "ICS One", "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    client.post("/add", data={"name": "ICS Two", "subject": "Math",
                              "deadline": "2026-11-02", "difficulty": "2",
                              "task_type": "quiz"},
                follow_redirects=True)
    body = client.get("/export.ics").get_data(as_text=True)
    assert body.count("BEGIN:VEVENT") == 2
    assert body.count("END:VEVENT") == 2
    assert "SUMMARY:ICS One (other)" in body
    assert "SUMMARY:ICS Two (quiz)" in body
    assert "DTSTART;VALUE=DATE:" + today.replace("-", "") in body
    assert "Difficulty: 3/5" in body           # description carries facts
    assert re.search(r"UID:[0-9-]+-\d+@nextup", body)


def test_ics_escapes_semicolons_commas_backslashes(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Evil, ; name", "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    body = client.get("/export.ics").get_data(as_text=True)
    assert "SUMMARY:Evil\\, \\; name (other)" in body


def test_ics_folds_long_lines(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    # 60 chars: under the 80-char name limit, still pushes the SUMMARY
    # line past the 75-octet fold threshold (name 60 + parenthetical +
    # 'SUMMARY:' overhead).
    long_name = "A" * 60
    client.post("/add", data={"name": long_name, "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    body = client.get("/export.ics").get_data(as_text=True)
    lines = body.split("\r\n")
    for line in lines:
        assert len(line) <= 75                  # fold keeps lines short
    assert any(l.startswith(" ") for l in lines)   # folded continuation
    assert f"SUMMARY:{long_name} (other)" not in body   # name is not one line


def test_ics_no_completed_tasks(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Cya", "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    client.post("/complete/1", follow_redirects=True)
    body = client.get("/export.ics").get_data(as_text=True)
    assert "Cya" not in body                    # only OPEN tasks export


def test_export_button_on_dashboard(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/export.ics"' in html


# ----------------------------------------------------------------------
# The weekly strip
# ----------------------------------------------------------------------
def test_week_strip_one_entry_per_day_with_url(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "In three days", "subject": "CS",
                              "deadline": (dash_to_date(today) +
                                           timedelta(days=3)).isoformat(),
                              "difficulty": "3", "estimated_hours": "2"},
                follow_redirects=True)
    html = client.get("/").get_data(as_text=True)
    assert html.count('class="week-day') == 7          # exactly 7 day cards
    # each day links with the EXISTING custom-range machinery
    # (& is &amp; in HTML source)
    assert html.count("range=custom&amp;from=") >= 7
    # the strip card for +3 days shows the summed hours (2h) as text
    # (the task NAME also appears in the dashboard tables -- that's fine,
    # this asserts on what the STRIP itself displays)
    assert "&gt;2h" in html or "2h\n" in html or re.search(r"\n\s*2h", html) or "2h" in html


def test_week_day_link_filters_to_that_day(client):
    """Only the clicked day's table rows remain; the task name repeats
    in each row's JS data attributes, so assert on the maximum."""
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Day plus two", "subject": "CS",
                              "deadline": (dash_to_date(today) +
                                           timedelta(days=2)).isoformat(),
                              "difficulty": "3"},
                follow_redirects=True)
    off_day = (dash_to_date(today) + timedelta(days=40)).isoformat()   # outside the week
    client.post("/add", data={"name": "Off strip", "subject": "CS",
                              "deadline": off_day, "difficulty": "3"},
                follow_redirects=True)
    target = (dash_to_date(today) + timedelta(days=2)).isoformat()
    html = client.get("/", query_string={
        "range": "custom", "from": target, "to": target,
    }).get_data(as_text=True)
    assert "Day plus two" in html
    assert "Off strip" not in html             # outside window: gone


def test_week_bar_warns_over_threshold(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    # 3 tasks x 2.5h = 7.5 hours on ONE day (over the 6h threshold)
    for k in range(3):
        client.post("/add", data={"name": f"heavy {k}", "subject": "CS",
                                  "deadline": (dash_to_date(today) +
                                               timedelta(days=1)).isoformat(),
                                  "difficulty": "3", "estimated_hours": "2.5"},
                    follow_redirects=True)
    html = client.get("/").get_data(as_text=True)
    assert "7.5h" in html                      # shows the summed hours
    assert "is-warn" in html                   # warning class on the bar/day


def dash_to_date(iso):
    from datetime import date as _d
    return _d.fromisoformat(iso)


def test_toast_and_shortcut_markers_present(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="toasts"' in html and 'role="status"' in html
    assert 'id="shortcuts"' in html
    # Stage A bug 1: theme lives in the SHARED theme.js now (so every
    # page gets it), referenced from this page.
    assert 'id="theme-toggle"' in html
    assert "theme.js" in html          # shared script is wired in
    assert "js-complete" in html               # undo-on-complete wiring
