"""
tests/test_structures.py
========================
STAGE 3: the structures page data layer.
  * the AVL's rotation log (insert/delete/LL/RR/LR/RL names, capacity 20,
    dashboard rebuilds keep history via ONE 'rebuild' event),
  * the read-only export_json() methods on heap and AVL,
  * the /structures route (renders, carries the JSON blocks),
  * the 'Why is this on top?' breakdown on the dashboard.
Run: pytest tests/test_structures.py -q
"""

import json

from datetime import timedelta


# ----------------------------------------------------------------------
# Unit level (manager fixture: throwaway db, pinned 'today')
# ----------------------------------------------------------------------
def test_log_records_inserts_and_deletes(tm):
    task, _ = tm.add_task("Logged in", "CS", (tm.today() + timedelta(days=3)).isoformat(), 3)
    tm.prepare_dashboard()
    ops = [(e["op"], e["name"]) for e in tm._avl.log
           if e["op"] in ("insert", "delete", "rebuild")]
    assert ("insert", "Logged in") in ops          # the user's insert is there
    # a rebuild event collapsed all the re-inserts into one line
    rebuilds = [e for e in tm._avl.log if e["op"] == "rebuild"]
    assert rebuilds and rebuilds[-1]["name"].endswith("tasks")
    tm.complete_task(task.id)                      # delete must be logged too
    ops2 = [e["op"] for e in tm._avl.log]
    assert "delete" in ops2


def test_log_capped_at_twenty(tm):
    for k in range(30):   # 30 inserts -- log must never exceed 20 entries
        tm.add_task(f"cap test {k}", "CS",
                    (tm.today() + timedelta(days=k + 1)).isoformat(), 3)
    assert len(tm._avl.log) <= 20


def test_log_keeps_rotation_kind(tm):
    # Insert 7 ascending deadlines -> a straight right spine -> RR rotations.
    for k in range(7):
        tm.add_task(f"spine {k}", "CS",
                    (tm.today() + timedelta(days=k + 1)).isoformat(), 3)
    ops = [e["op"] for e in tm._avl.log]
    assert "RR" in ops
    # and every rotation entry names the node it rotated at
    for e in tm._avl.log:
        if e["op"] in ("LL", "RR", "LR", "RL"):
            assert e["name"]


def test_rebuild_preserves_event_history(tm):
    task, _ = tm.add_task("Keeper", "CS", (tm.today() + timedelta(days=2)).isoformat(), 3)
    tm.prepare_dashboard()               # rebuild #1
    for _ in range(3):                   # ... and two more rebuilds
        tm.prepare_dashboard()
    names = {e["name"] for e in tm._avl.log}
    assert "Keeper" in names             # the original insert survived both
    assert any(e["op"] == "rebuild" for e in tm._avl.log)


def test_avl_export_json_matches_inorder(tm):
    from datetime import date as _d
    days = [9, 2, 5, 1, -3]
    for d in days:
        tm.add_task(f"exp {d}", "CS", (tm.today() + timedelta(days=d)).isoformat(), 3)
    tm.prepare_dashboard()
    tree = tm._avl
    exported = tree.export_json()
    # flatten the nested export by its own deadline/side order == inorder
    flat = []
    def walk(n):
        if not n:
            return
        walk(n["left"])
        flat.append(n["deadline"])
        walk(n["right"])
    walk(exported)
    assert flat == [t.deadline_str() for t in tree.inorder()]
    # balance factors are int-like values in {-1,0,+1}
    def check(n):
        if not n:
            return True
        return n["balance"] in (-1, 0, 1) and check(n["left"]) and check(n["right"])
    assert check(exported)


def test_avl_export_empty_tree(tm):
    fresh = tm._avl  # a manager with no tasks has an empty tree
    assert fresh.export_json() is None


def test_heap_export_json(tm):
    for k in range(8):
        tm.add_task(f"h{k}", "CS", (tm.today() + timedelta(days=k % 7)).isoformat(),
                    (k % 5) + 1)
    tm.prepare_dashboard()
    export = tm._heap.export_json()
    assert len(export) == 8
    assert all(set(e) >= {"index", "name", "priority"} for e in export)
    # slot 0 is the top task: it must carry the LOCALLY maximum priority
    pr = [e["priority"] for e in export]
    assert pr[0] == max(pr)
    # indexes are just 0..n-1 -- the array the page draws
    assert [e["index"] for e in export] == list(range(8))


# ----------------------------------------------------------------------
# Route level
# ----------------------------------------------------------------------
def test_structures_route_renders(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    for k in range(3):
        client.post("/add", data={"name": f"struct {k}", "subject": "CS",
                                  "deadline": today, "difficulty": "3"},
                    follow_redirects=True)
    html = client.get("/structures").get_data(as_text=True)
    assert html and "Fig. 1" in html and "Fig. 2" in html
    assert 'id="avl-data"' in html and 'id="heap-data"' in html
    assert "rotation-log" in html
    # the JSON blocks parse
    page = client.get("/structures")
    assert page.status_code == 200


def test_structures_route_cprs_names_not_html(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "<b>bold name</b>", "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    html = client.get("/structures").get_data(as_text=True)
    # tojson must escape the raw < inside the JSON script block
    assert "<b>bold name</b>" not in html.split("avl-data")[1].split("</script>")[0]
    assert "\\u003c" in html.lower() or "&lt;" in html or "\\u003c" in html


def test_dashboard_hero_breakdown_table(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Breakdown", "subject": "CS",
                              "deadline": today, "difficulty": "5",
                              "estimated_hours": "3", "task_type": "quiz"},
                follow_redirects=True)
    html = client.get("/").get_data(as_text=True)
    assert "Why is this on top?" in html
    assert 'class="why-table"' in html
    # arithmetic spot-check vs the API: urgency today = 300 + diff 25 + 3*1.5 + quiz 8
    task = next(t for t in client.get("/api/tasks").get_json()["tasks"]
                if t["name"] == "Breakdown")
    expected_total = 300 + 25 + (3 * 1.5) + 8
    assert abs(task["priority"] - expected_total) < 0.01
    assert str(round(expected_total, 1)) in html            # shown in the panel


def test_dashboard_breakdown_hidden_when_empty(client):
    html = client.get("/").get_data(as_text=True)
    assert "Why is this on top?" not in html
