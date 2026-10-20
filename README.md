# NextUp — Academic Task Priority Engine

**Developers:** Group 7 (Aguillera, Juan Miguel B.; Arandia, Jedrick O.; Masangcay, Jun Lorenz C.)

NextUp is a Python/Flask web app that helps students prioritize academic deadlines automatically. Instead of a static to-do list, it scores each task by urgency, difficulty, estimated hours, and task type, then surfaces the single most important task to work on next.

---

## Key Features
- **Smart Priority Dashboard:** Highlights the top-priority task (*"Do This Next"*) with a score breakdown, search/subject/date filters, and an interactive cat mascot.
- **Workload Analytics:** 7-day workload bar chart (flags days over 6.0 hours) and an Academic Focus category breakdown.
- **Multi-User Accounts:** Student sign-up/log-in with isolated per-user SQLite task databases.
- **DSA Visualizer:** Live SVG views of the Max-Heap and AVL Tree (`/structures`).
- **Calendar Export:** Export open tasks to `.ics` (`/export.ics`).

---

## Tech Stack
- **Backend:** Python 3.11, Flask, Werkzeug (password hashing)
- **Database:** SQLite3 (`storage.py`) with parameterized queries
- **Frontend:** HTML5, CSS3, Vanilla JavaScript
- **Testing:** `pytest` (109 automated tests)

---

## Data Structures & Algorithms Implemented
1. **Max Heap (`heap.py`):** Powers the top-priority task card with `O(1)` `peek()`, `O(log n)` `remove()` and `update_priority()`, and `O(n)` Floyd's bottom-up `build()`.
2. **AVL Tree (`avl_tree.py`):** Keeps open tasks sorted by deadline with `O(log n)` insert/delete/search via `LL`, `RR`, `LR`, and `RL` rotations, plus `O(log n + m)` `range_query()` for date-window filtering.
3. **Stack (`stack.py`):** LIFO `UndoStack` storing recently deleted tasks for the 6.5-second undo window.
4. **Queue & Linked List (`event_queue.py`):** Bounded FIFO `EventQueue` backed by singly-linked nodes (`_QNode`) with `O(1)` `enqueue()` and `dequeue()` for the AVL event log.
5. **Greedy Algorithm (`scoring.py`):** `priority_score()` computes a weighted priority from urgency, difficulty, estimated hours, and task type so the heap always picks the highest-scoring task next.
6. **Dynamic Programming (`scoring.py`):** `plan_study_session()` uses 0/1 Knapsack DP to select the highest-priority subset of tasks that fits within a student's available study hours.
7. **Sorting / Tree Traversal (`heap.py`, `avl_tree.py`):** Uses `O(n)` Floyd's heapify (`build()`) for priority-queue reconstruction and `O(n)` AVL `inorder()` traversal to output tasks sorted by deadline.

---

## Project Structure
```
nextup/
├── app.py              # Flask routes & HTTP handlers
├── task_manager.py     # Coordinates MaxHeap, AVLTree, UndoStack, and SQLite
├── heap.py             # Hand-built Max-Heap
├── avl_tree.py         # Hand-built self-balancing AVL Tree
├── stack.py            # Hand-built LIFO UndoStack
├── event_queue.py      # Hand-built linked-list FIFO EventQueue
├── scoring.py          # Priority scoring & 0/1 Knapsack DP planner
![alt text](image.png)├── storage.py          # SQLite persistence (TaskStore, UserStore)
├── task.py             # Task data model
├── templates/          # HTML templates (index, structures)
├── static/             # CSS, JS, mascot & logo assets
└── tests/              # Automated pytest suite
```

---

## How to Run
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the Flask app
python app.py
# Open http://127.0.0.1:5000

# 3. Run the test suite
py -3.11 -m pytest -q
```
