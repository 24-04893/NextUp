"""
tests/test_filters.py
=====================
STAGE 2: search, filters, and the pruned AVL range_query.

Covers:
  * the visited-vs-total pruning counter (a narrow window MUST visit
    far fewer nodes than a full inorder walk),
  * subject chips + name search via the routes,
  * the 'today' and 'week' and custom date shortcuts,
  * sorted order SURVIVING every filter,
Run: pytest tests/test_filters.py -q
"""

from datetime import timedelta

import pytest


# ----------------------------------------------------------------------
# Unit level: the pruning counter (uses pinned 'today' from the tm fixture)
# ----------------------------------------------------------------------
def test_range_query_visits_far_fewer_than_total(tm):
    from datetime import date
    from avl_tree import AVLTree  # noqa: F401  (docs link for readers)
    for k in range(60):           # 60 tasks, deadlines spread over 60 days
        tm.add_task(f"spread {k}", "CS",
                    (tm.today() + timedelta(days=k)).isoformat(), 3)
    # Rebuild the tree exactly like prepare_dashboard does.
    tm.prepare_dashboard()
    tree = tm._avl
    total = tree.node_count()
    assert total == 60
    # A ONE-DAY window: an O(n) walk would visit all 60; pruning should
    # only follow the two boundary paths (~ 2 * log2(60) ~ 12).
    tree.range_query(tm.today() + timedelta(days=30),
                     tm.today() + timedelta(days=30) + timedelta(days=0))
    visited = tree.visited
    assert 0 < visited < total                 # pruned... something
    assert visited <= total - 30               # ...at least half
    # An empty window outside ALL deadlines visits ~ just the boundary path.
    tree.range_query(tm.today() + timedelta(days=500),
                     tm.today() + timedelta(days=501))
    assert tree.visited < total
    # A full-span window (covering EVERY stored deadline 0..59) visits
    # everything -- no subtree can be ruled out.
    tree.range_query(tm.today() - timedelta(days=50),
                     tm.today() + timedelta(days=100))
    assert tree.visited == total


def test_visited_counter_resets_between_queries(tm):
    for k in range(10):
        tm.add_task(f"t{k}", "CS", (tm.today() + timedelta(days=k)).isoformat(), 3)
    tm.prepare_dashboard()
    tree = tm._avl
    tree.range_query(tm.today(), tm.today())            # small
    small_visit = tree.visited
    tree.range_query(tm.today() - timedelta(days=10),
                     tm.today() + timedelta(days=10))   # full span
    assert tree.visited == 10 and small_visit < tree.visited


# ----------------------------------------------------------------------
# Route level: chips, search, date shortcuts (via /api for easy asserts)
# ----------------------------------------------------------------------
def _seed_things(client):
    """Three tasks; follow_redirects on every POST so no flash text from
    the add step leaks into the assertions below."""
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Optics quiz", "subject": "Physics",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    client.post("/add", data={"name": "Essay outline", "subject": "History",
                              "deadline": today, "difficulty": "2"},
                follow_redirects=True)
    client.post("/add", data={"name": "Optics homework", "subject": "Physics",
                              "deadline": today, "difficulty": "2"},
                follow_redirects=True)
    return today


def test_search_filter_html(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Optics quiz", "subject": "Physics",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    client.post("/add", data={"name": "Essay outline", "subject": "History",
                              "deadline": today, "difficulty": "2"},
                follow_redirects=True)
    html = client.get("/", query_string={"q": "optics"}).get_data(as_text=True)
    assert "Optics quiz" in html and "Essay outline" not in html
    assert "Showing 1 of 2" in html


def test_subject_chip_filter(client):
    _seed_things(client)
    html = client.get("/", query_string={"subject": "Physics"}).get_data(as_text=True)
    assert "Optics homework" in html and "Essay outline" not in html
    # chips exist and are built from live subjects with counts
    assert "Physics (2)" in html and "History (1)" in html


def test_search_case_insensitive(client):
    _seed_things(client)
    data = client.get("/api/tasks", query_string={"q": "OPTICS"}).get_json()
    names = {t["name"] for t in data["tasks"]}
    assert names == {"Optics quiz", "Optics homework"}


def test_today_shortcut(client):
    """25 spread-out tasks: ONE due today, the rest on distinct days
    ahead. A one-day window can only prune tiny trees (the boundary
    paths reach most nodes), so this needs enough leaves that
    ~2*log2(n) visited < n shows up in the JSON stats."""
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Now", "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    for k in range(1, 24):                        # deadlines: +1 .. +23 days
        client.post("/add", data={"name": f"Spread {k}", "subject": "CS",
                                  "deadline": (dash_to_date(today) +
                                               timedelta(days=k)).isoformat(),
                                  "difficulty": "3"},
                    follow_redirects=True)
    data = client.get("/api/tasks", query_string={"range": "today"}).get_json()
    names = {t["name"] for t in data["sorted_list"]}
    assert names == {"Now"}
    assert data["range_stats"]["total"] == 24    # tree still holds all
    assert data["range_stats"]["visited"] < 24   # pruning visible in JSON


def dash_to_date(iso):
    """Tiny helper: 'YYYY-MM-DD' -> date, for building later deadlines."""
    from datetime import date as _d
    return _d.fromisoformat(iso)


def test_week_shortcut(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "This wk", "subject": "CS",
                              "deadline": today, "difficulty": "1"},
                follow_redirects=True)
    client.post("/add", data={"name": "In 6 days", "subject": "CS",
                              "deadline": "2026-10-26", "difficulty": "1"},
                follow_redirects=True)
    client.post("/add", data={"name": "Beyond", "subject": "CS",
                              "deadline": "2026-10-27", "difficulty": "1"},
                follow_redirects=True)
    data = client.get("/api/tasks", query_string={"range": "week"}).get_json()
    names = {t["name"] for t in data["sorted_list"]}
    assert names == {"This wk", "In 6 days"}      # inclusive on day 6


def test_custom_date_range_inclusive_endpoints(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Day none", "subject": "CS",
                              "deadline": today, "difficulty": "1"},
                follow_redirects=True)
    client.post("/add", data={"name": "Day three", "subject": "CS",
                              "deadline": "2026-10-23", "difficulty": "1"},
                follow_redirects=True)
    html = client.get("/", query_string={
        "range": "custom", "from": today, "to": "2026-10-23",
    }).get_data(as_text=True)
    assert "Day none" in html and "Day three" in html     # BOTH boundaries


def test_inverted_custom_range_warns_and_shows_all(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Stay visible", "subject": "CS",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    html = client.get("/", query_string={
        "range": "custom", "from": "2026-10-30", "to": "2026-10-02",
    }).get_data(as_text=True)
    assert "Stay visible" in html                       # filter ignored
    assert "was after" in html                          # gentle warning flash


def test_bad_custom_date_does_not_crash(client):
    html = client.get("/", query_string={
        "range": "custom", "from": "not-a-date", "to": "2026-10-02",
    }).get_data(as_text=True)
    assert html and "Could not read the custom dates" in html


def test_filters_preserve_sorted_order(client):
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Op A", "subject": "Phys",
                              "deadline": "2026-10-25", "difficulty": "3"},
                follow_redirects=True)
    client.post("/add", data={"name": "Op B", "subject": "Phys",
                              "deadline": today, "difficulty": "3"},
                follow_redirects=True)
    data = client.get("/api/tasks", query_string={"q": "op"}).get_json()
    deadlines = [t["deadline"] for t in data["sorted_list"]]
    assert deadlines == sorted(deadlines)               # calendar still sorted


def test_filters_stack_on_each_other(client):
    _seed_things(client)
    dash = client.get("/api/tasks").get_json()
    today = dash["today"]
    client.post("/add", data={"name": "Tomorrow optics", "subject": "Physics",
                              "deadline": "2026-11-30", "difficulty": "3"},
                follow_redirects=True)
    # subject=q combo: only "Physics" AND name contains optics, in window
    data = client.get("/api/tasks", query_string={
        "subject": "Physics", "q": "optics", "range": "today"}).get_json()
    names = {t["name"] for t in data["tasks"]}
    assert names == {"Optics quiz", "Optics homework"}


def test_subject_chip_links_survive_q(client):
    """Clicking a chip must NOT throw away the typed search."""
    _seed_things(client)
    html = client.get("/", query_string={"q": "optics", "subject": "Physics"}).get_data(as_text=True)
    # the search box still shows the query when filters stack
    assert 'value="optics"' in html
