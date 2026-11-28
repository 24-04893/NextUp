"""
app.py — Flask routes for NextUp (all DSA/business logic lives in TaskManager).
"""

import base64
import json
import os
import random
import uuid
import zlib
from datetime import date, timedelta, datetime, timezone

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, Response, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

if __package__:
    from .task import Task
    from .task_manager import TaskManager
    from .storage import UserStore
    from .scoring import DIFFICULTY_MAX, HOURS_CAP, URGENCY_DECAY_K, score_breakdown, plan_study_session
    from .pdf_export import generate_task_pdf, generate_tasks_list_pdf, safe_pdf_filename
else:
    from task import Task
    from task_manager import TaskManager
    from storage import UserStore
    from scoring import DIFFICULTY_MAX, HOURS_CAP, URGENCY_DECAY_K, score_breakdown, plan_study_session
    from pdf_export import generate_task_pdf, generate_tasks_list_pdf, safe_pdf_filename

app = Flask(__name__)
# flash() signs its one-shot cookies; any non-empty string works. This is a
# classroom app with no accounts, so a fixed dev key is fine and keeps the
# setup simple.
app.secret_key = "nextup-dev-flash-secret"

# NEXTUP_DB_FILE env var lets tests (and you) redirect the database path.
manager = TaskManager(os.environ.get("NEXTUP_DB_FILE"))
_user_stores = {}
_user_managers = {}


def _get_user_store():
    """Return the UserStore living in the same SQLite file as `manager`."""
    db_path = manager.store.db_path
    store = _user_stores.get(db_path)
    if store is None:
        store = UserStore(db_path)
        _user_stores[db_path] = store
    return store


def current_user():
    """Return the logged-in student's dict, demo profile, or None."""
    uid = session.get("user_id")
    if uid is not None:
        return _get_user_store().get_by_id(uid)
    if session.get("demo_id"):
        return session.get("demo_user")
    return None


def current_manager():
    """Return the logged-in student's (or demo session's) isolated TaskManager,
    or the default `manager` when no student is logged in."""
    user = current_user()
    if user is None:
        return manager
    base_dir = os.path.dirname(os.path.abspath(manager.store.db_path))
    demo_id = session.get("demo_id")
    if demo_id and session.get("user_id") is None:
        user_db = os.path.join(base_dir, f"nextup_demo_{demo_id}.db")
    else:
        user_db = os.path.join(base_dir, f"nextup_user_{user['id']}.db")
    mgr = _user_managers.get(user_db)
    if mgr is None:
        mgr = TaskManager(user_db, legacy_json="")
        _user_managers[user_db] = mgr
    # On Vercel serverless, /tmp is ephemeral across instances; hydrate from signed session cookie if empty.
    if os.environ.get("VERCEL") and not mgr.store.load_all() and session.get("vercel_tasks"):
        try:
            raw = zlib.decompress(base64.b64decode(session["vercel_tasks"]))
            items = json.loads(raw.decode("utf-8"))
            if isinstance(items, list) and items:
                tasks = [Task.from_dict(d) for d in items]
                mgr.store.save_all(tasks)
                mgr = TaskManager(user_db, legacy_json="")
                _user_managers[user_db] = mgr
        except Exception:
            pass
    return mgr


@app.after_request
def _no_cache_for_dynamic_views(response):
    """Prevent browsers from caching one student's dashboard for another."""
    if os.environ.get("VERCEL") and request.method == "POST" and not request.path.startswith("/auth/logout"):
        try:
            mgr = current_manager()
            tasks = mgr.store.load_all()
            payload = json.dumps([t.to_dict() for t in tasks], separators=(",", ":")).encode("utf-8")
            encoded = base64.b64encode(zlib.compress(payload, level=6)).decode("ascii")
            if len(encoded) < 3400:
                session["vercel_tasks"] = encoded
        except Exception:
            pass
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


# ----------------------------------------------------------------------
# Badge helper: red = overdue, orange = <=2 days, yellow = <=7, green = later
# ----------------------------------------------------------------------
def badge_for(task, today):
    """Map task + today -> (CSS badge class, days_left). O(1)."""
    days_left = (task.deadline - today).days
    if task.completed:
        badge = "badge-done"            # grey-green: already finished
    elif days_left < 0:
        badge = "badge-red"             # OVERDUE
    elif days_left <= 2:
        badge = "badge-orange"          # due today or within 2 days
    elif days_left <= 7:
        badge = "badge-yellow"          # within a week
    else:
        badge = "badge-green"           # later / safe
    return badge, days_left


def hero_explanation(task, today):
    """'Why is this on top?' WSM breakdown for the hero card. O(1).
    Uses the same score_breakdown() the score was built from — explanation never drifts."""
    bd = score_breakdown(task, today)
    norm = bd["normalized"]
    w = bd["weights"]
    days_left = bd["days_left"]
    due_time = task.deadline_time or "23:59"
    due_label = task.deadline.strftime("%b %d").replace(" 0", " ") + f" {due_time}"
    if days_left < 0:
        urgency_raw = f"OVERDUE by {abs(days_left):.2f}d (due {due_label})"
    elif abs(days_left) < 1e-6:
        urgency_raw = f"Due now ({due_label})"
    else:
        urgency_raw = f"{days_left:.2f}d left (due {due_label})"

    rows = [
        {
            "factor": "Urgency",
            "raw": urgency_raw,
            "norm": f"{norm['urgency']:.2f}",
            "weight": f"{w['urgency']:.2f}",
            "weighted": f"{bd['urgency']:.2f}",
        },
        {
            "factor": "Type",
            "raw": f"'{task.task_type.capitalize()}'",
            "norm": f"{norm['type']:.2f}",
            "weight": f"{w['type']:.2f}",
            "weighted": f"{bd['type']:.2f}",
        },
        {
            "factor": "Difficulty",
            "raw": f"{task.difficulty}/5 steps",
            "norm": f"{norm['difficulty']:.2f}",
            "weight": f"{w['difficulty']:.2f}",
            "weighted": f"{bd['difficulty']:.2f}",
        },
        {
            "factor": "Size",
            "raw": f"{task.hours_str()} {'hour' if task.estimated_hours == 1 else 'hours'} (cap {HOURS_CAP:g}h)",
            "norm": f"{norm['hours']:.2f}",
            "weight": f"{w['hours']:.2f}",
            "weighted": f"{bd['hours']:.2f}",
        },
    ]
    eq = {
        "k": f"{URGENCY_DECAY_K:.2f}",
        "days_left": f"{days_left:.2f}",
        "u_norm": f"{norm['urgency']:.2f}",
        "diff": str(task.difficulty),
        "diff_max": f"{DIFFICULTY_MAX:g}",
        "d_norm": f"{norm['difficulty']:.2f}",
        "hours": task.hours_str(),
        "hours_cap": f"{HOURS_CAP:g}",
        "s_norm": f"{norm['hours']:.2f}",
        "task_type": task.task_type.capitalize(),
        "t_norm": f"{norm['type']:.2f}",
        "w_u": f"{w['urgency']:.2f}",
        "w_d": f"{w['difficulty']:.2f}",
        "w_s": f"{w['hours']:.2f}",
        "w_t": f"{w['type']:.2f}",
        "u_weighted": f"{bd['urgency']:.2f}",
        "d_weighted": f"{bd['difficulty']:.2f}",
        "s_weighted": f"{bd['hours']:.2f}",
        "t_weighted": f"{bd['type']:.2f}",
        "total": f"{bd['total']:.2f}",
    }
    line = (
        f"WSM score {bd['total']:.2f}/100: Urgency {bd['urgency']:.2f} "
        f"({w['urgency']:.2f}x{norm['urgency']:.2f}) + Type {bd['type']:.2f} "
        f"({w['type']:.2f}x{norm['type']:.2f}) + Difficulty {bd['difficulty']:.2f} "
        f"({w['difficulty']:.2f}x{norm['difficulty']:.2f}) + Size {bd['hours']:.2f} "
        f"({w['hours']:.2f}x{norm['hours']:.2f})."
    )
    return {
        "urgency": round(bd["urgency"], 2),
        "type": round(bd["type"], 2),
        "difficulty": round(bd["difficulty"], 2),
        "hours": round(bd["hours"], 2),
        "total": round(bd["total"], 2),
        "total_str": f"{bd['total']:.2f}",
        "weight_sum": f"{sum(w.values()):.2f}",
        "rows": rows,
        "eq": eq,
        "why": line,
    }


def decorate(tasks, today):
    """Convert Task objects into template/API-friendly dicts. O(n)."""
    out = []
    for t in tasks:
        badge, days_left = badge_for(t, today)
        out.append({
            "id": t.id, "name": t.name, "subject": t.subject,
            "deadline": t.deadline_str(), "difficulty": t.difficulty,
            "estimated_hours": t.estimated_hours, "hours_str": t.hours_str(),
            "task_type": t.task_type, "deadline_time": t.deadline_time,
            "completed": t.completed, "completed_at": t.completed_at,
            "priority": round(t.priority, 2),
            "badge": badge, "days_left": days_left,
        })
    return out


# ----------------------------------------------------------------------
# Filter plumbing (query-string -> template-ready values)
# ----------------------------------------------------------------------
def _filters_from_args(today):
    """Parse GET filter query params into normalized values; bad dates fall back gracefully. O(1)."""
    subject = request.args.get("subject", "").strip() or None
    query = request.args.get("q", "").strip() or None
    mode = request.args.get("range", "").strip()
    from_text = request.args.get("from", "").strip()
    to_text = request.args.get("to", "").strip()
    start = end = None
    warn = None
    if mode == "today":
        start = end = today
    elif mode == "week":
        start = today
        end = today + timedelta(days=6)     # today through today+6
    elif mode == "custom":
        try:
            start = date.fromisoformat(from_text)
            end = date.fromisoformat(to_text)
        except ValueError:
            warn = "Could not read the custom dates (need YYYY-MM-DD) -- " \
                   "showing all tasks instead."
            start = end = None
        else:
            if start > end:
                warn = "'From' was after 'To' -- showing all tasks instead."
                start = end = None
    return {"subject": subject, "query": query, "mode": mode,
            "start": start, "end": end, "warn": warn,
            "from": from_text, "to": to_text}


def _filter_url(**overrides):
    """Build a /-link that KEEPS every current filter and applies the
    `overrides` (pass None to drop one). Keeps the template dumb."""
    params = {"subject": request.args.get("subject", "").strip() or None,
              "q": request.args.get("q", "").strip() or None,
              "range": request.args.get("range", "").strip() or None,
              "from": request.args.get("from", "").strip() or None,
              "to": request.args.get("to", "").strip() or None}
    params.update(overrides)
    clean = {k: v for k, v in params.items() if v}
    return url_for("index", **clean)


# WEEK_HOURS_WARN: total estimated hours per day that triggers an orange warning bar.
WEEK_HOURS_WARN = 6.0


def _week_overview(views, today):
    """Today..+6 workload facts per day for the weekly strip. O(n) over
    the open calendar list (already sorted by the AVL inorder traversal)."""
    buckets = {today + timedelta(days=i): {"count": 0, "hours": 0.0, "tasks": []}
               for i in range(7)}
    for t in views["sorted_list"]:               # open tasks only
        if t.deadline in buckets:
            buckets[t.deadline]["count"] += 1
            buckets[t.deadline]["hours"] += t.estimated_hours
            buckets[t.deadline]["tasks"].append({
                "name": t.name,
                "subject": t.subject or "",
                "task_type": t.task_type,
                "hours": round(t.estimated_hours, 1),
                "deadline_time": t.deadline_time or "",
            })
    days = []
    peak = max((b["hours"] for b in buckets.values()), default=0.0) or 1.0
    for i in range(7):
        d = today + timedelta(days=i)
        b = buckets[d]
        hours = round(b["hours"], 1)
        days.append({
            "iso": d.isoformat(),
            "name": d.strftime("%a"),
            "date": d.day,
            "is_today": i == 0,
            "count": b["count"],
            "hours": hours,
            "warn": hours > WEEK_HOURS_WARN,
            "bar": round(hours / peak * 100),    # bar height, scaled
            "tasks": b["tasks"],
            "url": _filter_url(range="custom",
                               **{"from": d.isoformat(), "to": d.isoformat()}),
        })
    return days


def _academic_focus(views, today):
    """Compute real category breakdown and on-track percentage for the
    Workload tab's Academic Focus donut chart from open tasks."""
    open_tasks = views["sorted_list"]
    total = len(open_tasks)
    overdue = sum(1 for t in open_tasks if t.deadline < today)
    on_track_pct = round(((total - overdue) / total) * 100) if total > 0 else 100

    cats = [
        {"key": "tasks", "label": "Tasks", "color": "#f97316", "tasks": []},
        {"key": "quiz", "label": "Quiz", "color": "#fbbf24", "tasks": []},
        {"key": "projects", "label": "Projects", "color": "#1e293b", "tasks": []},
        {"key": "other", "label": "Labs / Others", "color": "#334155", "tasks": []},
    ]
    cat_map = {c["key"]: c for c in cats}

    for t in open_tasks:
        tt = (t.task_type or "").lower()
        if tt in ("assignment", "activity"):
            key = "tasks"
        elif tt in ("quiz", "exam"):
            key = "quiz"
        elif tt == "lab":
            key = "projects"
        else:
            key = "other"
        cat_map[key]["tasks"].append({
            "name": t.name,
            "subject": t.subject or "",
            "deadline": t.deadline.isoformat(),
            "deadline_time": t.deadline_time or "",
            "hours": round(t.estimated_hours, 1),
        })

    circumference = 289.03  # 2 * pi * 46
    offset = 0.0
    non_zero = [c for c in cats if c["tasks"]]
    for idx, c in enumerate(cats):
        count = len(c["tasks"])
        c["count"] = count
        if total > 0 and count > 0:
            if c is non_zero[-1]:
                dash = round(max(0.0, circumference - offset), 2)
            else:
                dash = round((count / total) * circumference, 2)
            c["dash"] = dash
            c["offset"] = round(-offset, 2)
            offset += dash
        else:
            c["dash"] = 0.0
            c["offset"] = 0.0

    return {
        "total": total,
        "overdue": overdue,
        "on_track_pct": on_track_pct,
        "circumference": circumference,
        "categories": cats,
    }
@app.route("/auth/signup", methods=["POST"])
def auth_signup():
    """Create a new student account and start an isolated session."""
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    program = (data.get("program") or "").strip()
    year_level = (data.get("yearLevel") or data.get("year_level") or "").strip()
    password = data.get("password") or ""

    if not name or not program or not year_level or not password:
        return jsonify({"ok": False, "error": "Please fill in Name, Program, Year Level, and Password."}), 400
    if len(name) > 80 or len(program) > 80 or len(year_level) > 40:
        return jsonify({"ok": False, "error": "Input length exceeds maximum allowed."}), 400

    pw_hash = generate_password_hash(password)
    try:
        user = _get_user_store().create_user(name, program, year_level, pw_hash)
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 409

    session["user_id"] = user["id"]
    return jsonify({"ok": True, "user": user})


@app.route("/auth/login", methods=["POST"])
def auth_login():
    """Authenticate an existing student and switch to their task store."""
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""

    if not name or not password:
        return jsonify({"ok": False, "error": "Please enter your Name and Password."}), 400

    user, pw_hash = _get_user_store().authenticate(name)
    if user is None or not check_password_hash(pw_hash, password):
        return jsonify({"ok": False, "error": "Invalid name or password."}), 401

    session["user_id"] = user["id"]
    return jsonify({"ok": True, "user": user})


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    """Log out the current student or exit demo mode."""
    session.pop("user_id", None)
    session.pop("demo_id", None)
    session.pop("demo_user", None)
    return jsonify({"ok": True})


DEMO_SUBJECT_TASKS = [
    ("CpE 411", "DSA AVL Tree & Max-Heap Lab"),
    ("CpE 414", "Feedback & Control Systems Problem Set"),
    ("Fili 102", "Pagsusuri ng Artikulo sa Disiplina"),
    ("CpE 413", "Mixed Signals & Sensors Quiz Prep"),
    ("CpE 415", "HDL Verilog Sequential Circuit Design"),
    ("CpE 412", "Cisco 1 Subnetting & VLAN Activity"),
    ("CpE 410", "Logic Circuits & K-Map Worksheet"),
    ("ENGG 416", "Research Methods Chapter 1-3 Review"),
]


@app.route("/auth/demo", methods=["POST"])
def auth_demo():
    """Start an isolated Demo Mode session with 1 randomized task per subject across 7 days."""
    session.pop("user_id", None)
    demo_id = uuid.uuid4().hex[:10]
    demo_user = {
        "id": 0,
        "name": "Demo Student",
        "program": "BS CpE",
        "yearLevel": "4th Year",
    }
    session["demo_id"] = demo_id
    session["demo_user"] = demo_user

    mgr = current_manager()
    today = mgr.today()
    day_offsets = [0, 1, 2, 3, 4, 5, 6, random.randint(0, 6)]
    random.shuffle(day_offsets)
    task_types = ["assignment", "lab", "quiz", "activity", "others",
                  "exam", "quiz", "lab"]
    random.shuffle(task_types)
    times = ["09:00", "10:30", "13:00", "15:00", "17:30", "19:00", "21:00", "23:59"]
    hours_pool = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

    for idx, (subject, title) in enumerate(DEMO_SUBJECT_TASKS):
        deadline_str = (today + timedelta(days=day_offsets[idx])).isoformat()
        mgr.add_task(
            name=title,
            subject=subject,
            deadline_text=deadline_str,
            difficulty=random.randint(1, 5),
            estimated_hours=random.choice(hours_pool),
            task_type=task_types[idx],
            deadline_time=random.choice(times),
        )

    return jsonify({"ok": True, "user": demo_user})


@app.route("/auth/me")
def auth_me():
    """Return the currently logged-in student profile, or null."""
    return jsonify({"user": current_user()})


@app.route("/")
def index():
    """The dashboard, optionally filtered. prepare_dashboard() re-scores
    everything against TODAY'S date and rebuilds the heap, so the page
    is always current; filter_dashboard() then narrows BOTH tables while
    keeping their baked-in sort order."""
    mgr = current_manager()
    args = _filters_from_args(mgr.today())
    if args["warn"]:
        flash(args["warn"], "warning")
    views = mgr.filter_dashboard(subject=args["subject"],
                                 query=args["query"],
                                 start=args["start"], end=args["end"])
    today = views["today"]
    visited, total_nodes = views["range_stats"]
    date_mode = args["mode"] in ("today", "week", "custom") and args["start"]

    # Chips: 'All subjects' + one per existing subject, with counts.
    chips = [{"label": "All subjects", "url": _filter_url(subject=None),
              "active": args["subject"] is None}]
    for s_name, s_count in views["subjects"]:
        chips.append({"label": f"{s_name} ({s_count})",
                      "url": _filter_url(subject=s_name),
                      "active": s_name == args["subject"]})
    date_buttons = [{"key": "today", "label": "Due today",
                     "url": _filter_url(range="today"),
                     "active": args["mode"] == "today"},
                    {"key": "week", "label": "This week",
                     "url": _filter_url(range="week"),
                     "active": args["mode"] == "week"}]

    open_total = (mgr.status()["open"])
    if views["top"] is not None:
        breakdown = hero_explanation(views["top"], today)
    else:
        breakdown = None
    # Weekly workload strip & academic focus donut data
    week = _week_overview(views, today)
    focus = _academic_focus(views, today)
    return render_template(
        "index.html",
        breakdown=breakdown,
        top_info=decorate([views["top"]], today)[0] if views["top"] else None,
        tasks=decorate(views["by_priority"], today),          # highest score first
        sorted_list=decorate(views["sorted_list"], today),    # earliest deadline first
        completed=decorate(views["completed"], today),
        status=mgr.status(),
        today=today,
        chips=chips,
        date_buttons=date_buttons,
        date_mode=date_mode,
        q_value=args["query"] or "",
        from_value=args["from"],
        to_value=args["to"],
        active_range=args["mode"],
        date_window=(args["start"].isoformat(), args["end"].isoformat())
            if date_mode else None,
        visited=visited, total_nodes=total_nodes,
        shown=len(views["by_priority"]), open_total=open_total,
        any_filter=bool(args["subject"] or args["query"] or date_mode),
        clear_url=url_for("index"),
        week=week,
        focus=focus,
        week_threshold=WEEK_HOURS_WARN,
        current_user=current_user(),
    )


@app.route("/add", methods=["POST"])
def add():
    """Validate and add a new task (warns on past deadlines). """
    mgr = current_manager()
    try:
        fields = mgr.parse_form(request.form)
        task, warnings = mgr.add_task(
            fields["name"], fields["subject"], fields["deadline"],
            fields["difficulty"], fields["estimated_hours"],
            fields["task_type"], fields["deadline_time"])
    except ValueError as err:
        flash(str(err), "error")
        return redirect(url_for("index"))
    for warning in warnings:
        flash(warning, "warning")
    flash(f"Added '{task.name}'.", "ok")
    return redirect(url_for("index"))


@app.route("/edit/<int:task_id>", methods=["POST"])
def edit(task_id):
    """Validate and update an open task."""
    mgr = current_manager()
    try:
        task, warnings = mgr.edit_task(
            task_id,
            request.form.get("name", ""),
            request.form.get("subject", ""),
            request.form.get("deadline", ""),
            request.form.get("difficulty", ""),
            request.form.get("estimated_hours", 1),
            request.form.get("task_type", "other"),
            request.form.get("deadline_time"),
        )
    except ValueError as err:
        flash(str(err), "error")
        return redirect(url_for("index"))
    for warning in warnings:
        flash(warning, "warning")
    flash(f"Updated '{task.name}'.", "ok")
    return redirect(url_for("index"))


@app.route("/complete/<int:task_id>", methods=["POST"])
def complete(task_id):
    """Complete ANY task (the button on each row). TaskManager removes
    it from BOTH the heap and the AVL -- never hard-deleting it."""
    task = current_manager().complete_task(task_id)
    if task is None:
        flash("That task does not exist (or was already completed).", "error")
    else:
        flash(f"Completed '{task.name}'. Nice work!", "ok")
    return redirect(url_for("index"))


@app.route("/complete-top", methods=["POST"])
def complete_top():
    """Complete the most urgent open task via the heap's extract_max."""
    task = current_manager().complete_top()
    if task is None:
        flash("Nothing left to complete -- you are all caught up!", "ok")
    else:
        flash(f"Completed the top task: '{task.name}'.", "ok")
    return redirect(url_for("index"))


@app.route("/delete/<int:task_id>", methods=["POST"])
def delete(task_id):
    """Hard-delete a task from SQLite, dict, heap, and AVL; keeps a copy
    in the 6.5 s trash for POST /undo-delete/<id>."""
    task = current_manager().delete_task(task_id)
    if task is None:
        flash("Nothing to delete -- no task with that id.", "error")
    else:
        flash(f"DELETED '{task.name}'.", "ok")
    return redirect(url_for("index"))


@app.route("/undo-delete/<int:task_id>", methods=["POST"])
def undo_delete(task_id):
    """Restore a recently deleted task within the 6.5 s undo window."""
    task = current_manager().undelete_task(task_id)
    if task is None:
        flash("That delete can no longer be undone.", "error")
    else:
        flash(f"Restored '{task.name}'.", "ok")
    return redirect(url_for("index"))


@app.route("/restore/<int:task_id>", methods=["POST"])
def restore(task_id):
    """Move a completed task back to open in both heap and AVL."""
    task = current_manager().restore_task(task_id)
    if task is None:
        flash("Nothing to restore (unknown id, or already open).", "error")
    else:
        flash(f"Restored '{task.name}' -- it is back in the lists.", "ok")
    return redirect(url_for("index"))


@app.route("/structures")
def structures():
    """Visualizer for AVL tree, MaxHeap, and recent events."""
    mgr = current_manager()
    page = mgr.structures_page()
    return render_template(
        "structures.html",
        avl=page["avl"],
        heap=page["heap"],
        log=page["log"],
        stats=mgr.status(),
        current_user=current_user(),
    )


@app.route("/api/tasks")
def api_tasks():
    """JSON dump of everything the dashboard shows. Accepts the SAME
    filter query-string as '/' (subject/query/range/from/to), so
    the JSON mirrors the page exactly."""
    mgr = current_manager()
    args = _filters_from_args(mgr.today())
    views = mgr.filter_dashboard(subject=args["subject"],
                                 query=args["query"],
                                 start=args["start"], end=args["end"])
    today = views["today"]
    visited, total_nodes = views["range_stats"]
    return jsonify({
        "today": today.isoformat(),
        "status": mgr.status(),
        "filters": {"subject": args["subject"], "q": args["query"],
                    "range": args["mode"]},
        "range_stats": {"visited": visited, "total": total_nodes},
        "tasks": decorate(views["by_priority"], today),        # priority order
        "sorted_list": decorate(views["sorted_list"], today),  # deadline order
        "completed": decorate(views["completed"], today),
    })


@app.route("/export.ics")
def export_ics():
    r"""Export all open tasks as an RFC 5545 iCalendar (.ics) file.
    Uses CRLF line endings, <=75-octet line folding, proper text escaping,
    and stable UIDs per deadline+id. Read-only.
    """
    dash = current_manager().prepare_dashboard()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//NextUp//course project//EN"]
    # DTSTAMP must be UTC per RFC 5545
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    open_tasks = [t for t in dash["sorted_list"] if not t.completed]
    for t in open_tasks:
        lines += ["BEGIN:VEVENT",
                  f"UID:{t.deadline.isoformat()}-{t.id}@nextup",
                  f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{t.deadline.strftime('%Y%m%d')}",
                  _ics_line("SUMMARY", f"{t.name} ({t.task_type})"),
                  _ics_line("DESCRIPTION",
                            "Subject: " + t.subject + "\n"
                            "Difficulty: " + str(t.difficulty) + "/5\n"
                            "Estimated hours: " + f"{t.estimated_hours:g}"),
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    text = "\r\n".join(lines) + "\r\n"
    return Response(text, mimetype="text/calendar",
                    headers={"Content-Disposition":
                             "attachment; filename=nextup.ics"})


@app.route("/export/pdf/<int:task_id>")
def export_task_pdf(task_id):
    """Export a single task (with priority breakdown) as a downloadable PDF."""
    mgr = current_manager()
    task = mgr._tasks.get(task_id)
    if task is None:
        abort(404)
    today = mgr.today()
    task.priority = score_breakdown(task, today)["total"]
    breakdown = score_breakdown(task, today)
    pdf_bytes = generate_task_pdf(task, today, breakdown=breakdown)
    filename = safe_pdf_filename(task.name, fallback=f"task_{task.id}")
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/export/pdf")
def export_all_pdf():
    """Export all open tasks (ordered by priority) as a downloadable PDF."""
    mgr = current_manager()
    dash = mgr.prepare_dashboard()
    pdf_bytes = generate_tasks_list_pdf(dash["by_priority"], dash["today"])
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=nextup_tasks.pdf"},
    )


def _ics_line(name, value):
    """Escape and fold one RFC 5545 iCalendar content line at <=75 octets."""
    value = str(value).replace("\\", "\\\\").replace(";", "\\;")\
                      .replace(",", "\\,").replace(chr(10), "\\n")
    raw = f"{name}:{value}"
    if len(raw) <= 75:
        return raw
    folded, rest, at = [], raw, 75
    while len(rest) > at:
        cut = rest.rfind(" ", 0, at)          # fold at a space, politely
        if cut <= 0:
            cut = at                          # no space in range: hard cut
        folded.append(rest[:cut])
        rest = rest[cut:]                     # join below adds THE one space
        at = 74                               # continuation budget: 75 - 1
    folded.append(rest)
    return "\r\n ".join(folded)

@app.route("/api/top")
def api_top():
    """JSON: just the 'Do this next' card's data, or top: null."""
    dash = current_manager().prepare_dashboard()
    today = dash["today"]
    if dash["top"] is None:
        return jsonify({"top": None})
    return jsonify({"top": decorate([dash["top"]], today)[0]})


@app.route("/api/plan-session", methods=["POST"])
def api_plan_session():
    """Dynamic Programming (0/1 Knapsack) study planner for available hours."""
    data = request.get_json(silent=True) or request.form
    try:
        hours = float(data.get("hours", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Enter a valid number of hours."}), 400
    if hours <= 0 or hours > 24:
        return jsonify({"ok": False, "error": "Available hours must be between 0.5 and 24."}), 400

    dash = current_manager().prepare_dashboard()
    plan = plan_study_session(dash["by_priority"], hours)
    return jsonify({
        "ok": True,
        "hours": hours,
        "used_hours": plan["used_hours"],
        "total_score": plan["total_score"],
        "tasks": decorate(plan["selected"], dash["today"]),
    })


# dev server entry point -- Flask's reloader is perfect for a course project.
if __name__ == "__main__":
    app.run(debug=True)
