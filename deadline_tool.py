"""
Module 2: Deadline Tool
-------------------------
This is "Tool 1" of the agent's 3 tools.

Purpose: let the user add, update, or query deadlines (assignments,
projects, exams). This is the entry point for all deadline data —
the Reprioritization Tool (Module 4) and Agent Orchestration (Module 6)
read whatever this tool writes.

Design note: validation lives HERE, not in storage.py. storage.py just
persists whatever it's given (with basic DB-level checks). This tool is
the "gatekeeper" that makes sure only clean, sensible data gets in.
"""

import math
from datetime import date, timedelta
import storage

VALID_PRIORITIES = {"low", "medium", "high"}
VALID_STATUSES = {"pending", "done", "missed"}
VALID_CATEGORIES = {"assignment", "exam", "presentation", "project", "other"}


def add_deadline(task_name: str, due_date: str, estimated_hours: float, priority: str,
                 category: str = "other") -> dict:
    """
    Adds a new deadline.

    Args:
        task_name: short name of the task/assignment
        due_date: ISO date string (YYYY-MM-DD)
        estimated_hours: how many hours the user thinks it will take
        priority: 'low', 'medium', or 'high'
        category: kind of work ('assignment', 'exam', 'presentation',
                  'project', or 'other'). Memory (Module 5) uses this to
                  spot which kinds of deadline the user tends to miss.

    Returns:
        dict with status ("success" or "error") and a message.
    """
    if not task_name or not task_name.strip():
        return {"status": "error", "message": "task_name cannot be empty."}

    try:
        parsed_due = date.fromisoformat(due_date)
    except (ValueError, TypeError):
        return {"status": "error", "message": "due_date must be in YYYY-MM-DD format."}

    if parsed_due < date.today():
        return {"status": "error", "message": "due_date cannot be in the past."}
    # fromisoformat also accepts forms like 20261015; store one format only
    due_date = parsed_due.isoformat()

    try:
        estimated_hours = float(estimated_hours)
    except (ValueError, TypeError):
        return {"status": "error", "message": "estimated_hours must be a number."}

    if not math.isfinite(estimated_hours):
        return {"status": "error", "message": "estimated_hours must be a number."}

    if estimated_hours <= 0:
        return {"status": "error", "message": "estimated_hours must be greater than 0."}

    priority = priority.lower().strip() if priority else ""
    if priority not in VALID_PRIORITIES:
        return {"status": "error", "message": f"priority must be one of {sorted(VALID_PRIORITIES)}."}

    category = category.lower().strip() if category else "other"
    if category not in VALID_CATEGORIES:
        return {"status": "error", "message": f"category must be one of {sorted(VALID_CATEGORIES)}."}

    storage.add_deadline(task_name.strip(), due_date, estimated_hours, priority, category)

    return {
        "status": "success",
        "message": f"Added deadline '{task_name}' due {due_date} "
                   f"(est. {estimated_hours}h, priority: {priority}, category: {category})."
    }


def get_deadlines(status: str = None) -> dict:
    """
    Fetches deadlines, optionally filtered by status.

    Args:
        status: 'pending', 'done', or 'missed'. If None, returns all.
    """
    if status:
        status = status.lower().strip()
        if status not in VALID_STATUSES:
            return {"status": "error", "message": f"status must be one of {sorted(VALID_STATUSES)}."}

    deadlines = storage.get_deadlines(status)
    return {"status": "success", "deadlines": deadlines, "count": len(deadlines)}


def update_deadline_status(deadline_id: int, status: str) -> dict:
    """
    Updates a deadline's status (e.g. mark it 'done' once finished).

    Args:
        deadline_id: the ID of the deadline to update
        status: 'pending', 'done', or 'missed'
    """
    try:
        deadline_id = int(deadline_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": "deadline_id must be an integer."}

    status = status.lower().strip() if status else ""
    if status not in VALID_STATUSES:
        return {"status": "error", "message": f"status must be one of {sorted(VALID_STATUSES)}."}

    if not any(d["deadline_id"] == deadline_id for d in storage.get_deadlines()):
        return {"status": "error", "message": f"No deadline found with id {deadline_id}."}

    storage.update_deadline_status(deadline_id, status)
    return {"status": "success", "message": f"Deadline {deadline_id} marked as '{status}'."}


# ---------------------------------------------------------------------
# Tool schemas (for LLM function-calling in Module 6 - Agent Orchestration)
# ---------------------------------------------------------------------
ADD_DEADLINE_SCHEMA = {
    "name": "add_deadline",
    "description": "Add a new deadline (assignment, project, or exam) with a due date, "
                    "estimated hours of work, and priority level.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_name": {"type": "string", "description": "Short name of the task"},
            "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format"},
            "estimated_hours": {"type": "number", "description": "Estimated hours needed to complete it"},
            "priority": {"type": "string", "description": "Priority level", "enum": sorted(VALID_PRIORITIES)},
            "category": {"type": "string", "description": "Kind of work (optional, defaults to 'other')",
                         "enum": sorted(VALID_CATEGORIES)},
        },
        "required": ["task_name", "due_date", "estimated_hours", "priority"],
    },
}

GET_DEADLINES_SCHEMA = {
    "name": "get_deadlines",
    "description": "Retrieve current deadlines, optionally filtered by status "
                    "(pending, done, or missed).",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "Optional filter", "enum": sorted(VALID_STATUSES)},
        },
        "required": [],
    },
}

UPDATE_DEADLINE_STATUS_SCHEMA = {
    "name": "update_deadline_status",
    "description": "Update the status of an existing deadline (e.g. mark it done after finishing it).",
    "input_schema": {
        "type": "object",
        "properties": {
            "deadline_id": {"type": "integer", "description": "ID of the deadline to update"},
            "status": {"type": "string", "description": "New status", "enum": sorted(VALID_STATUSES)},
        },
        "required": ["deadline_id", "status"],
    },
}


# ---------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    storage.init_db()
    storage.reset_db()

    # dates are relative to today so the self-test never goes stale
    def days_from_now(n):
        return (date.today() + timedelta(days=n)).isoformat()

    # valid deadline
    print(add_deadline("DBMS Assignment", days_from_now(5), estimated_hours=5, priority="high"))

    # another valid deadline
    print(add_deadline("Presentation Prep", days_from_now(3), estimated_hours=3, priority="medium",
                       category="presentation"))

    # invalid category
    print(add_deadline("Mystery Task", days_from_now(4), estimated_hours=2, priority="low", category="chores"))

    # invalid due_date format
    print(add_deadline("Bad Date Task", "10-09-2026", estimated_hours=2, priority="low"))

    # invalid priority
    print(add_deadline("Urgent Task", days_from_now(4), estimated_hours=2, priority="urgent"))

    # past due date
    print(add_deadline("Old Task", "2020-01-01", estimated_hours=1, priority="low"))

    print("\nAll pending deadlines:")
    print(get_deadlines("pending"))

    print("\nMarking deadline 1 as done:")
    print(update_deadline_status(1, "done"))

    # non-existent deadline id
    print(update_deadline_status(999, "done"))

    print("\nAll deadlines after update:")
    print(get_deadlines())