"""
Module 7: Negotiation Tool
-----------------------------
This is the "negotiator" part of the Personal Deadline Negotiator Agent.

Purpose: the Reprioritization Tool (Module 4) only says WHICH deadlines are
at risk. This module answers the next two questions:
    1. "What should I work on each day?"      -> build_plan()
    2. "I can't make it all — what are my ways out?" -> get_negotiation_options()

For every deadline that doesn't fit, it lays out the concrete trade-offs:
defer a lower-priority task, ask for an extension, find more free time, or
hand in a reduced scope. It also lets the agent log what it recommended
(history table), so recommendations can later be compared with outcomes.

Design note: same split as Module 4 — this module only does the
deterministic scheduling math. Choosing WHICH option to recommend, and
explaining why, is the agent's job in Module 6.
"""

from datetime import date, timedelta
import storage
import memory as mem
from reprioritization_tool import PRIORITY_WEIGHT


def _resolve_today(as_of_date: str = None):
    """Returns (today_iso, None) or (None, error_dict) if as_of_date is malformed."""
    try:
        today = date.fromisoformat(as_of_date).isoformat() if as_of_date else date.today().isoformat()
    except (ValueError, TypeError):
        return None, {"status": "error", "message": "as_of_date must be in YYYY-MM-DD format."}
    return today, None


def _allocate(today: str):
    """
    Shared scheduling pass: hands each free hour to the earliest pending
    deadline first (same rule as Module 4's feasibility check).

    Returns:
        pace: the pace multiplier used
        tasks: pending deadlines, each with hours_needed, slots {day: hours}, shortfall
        free: {day: hours still unassigned} for every logged day from today onward
    """
    pace = mem.get_pace_multiplier()
    free = {
        r["date"]: r["available_hours"]
        for r in storage.get_availability()
        if r["date"] >= today
    }

    tasks = []
    for d in storage.get_deadlines(status="pending"):  # ordered by due date
        hours_needed = round(d["estimated_hours"] * pace, 2)
        left = hours_needed
        slots = {}
        for day in sorted(free):
            if day > d["due_date"] or left <= 0:
                break
            take = min(free[day], left)
            if take > 0:
                slots[day] = round(take, 2)
                free[day] = round(free[day] - take, 2)
                left = round(left - take, 2)

        tasks.append({
            "deadline_id": d["deadline_id"],
            "task_name": d["task_name"],
            "due_date": d["due_date"],
            "priority": d["priority"],
            "category": d["category"],
            "hours_needed": hours_needed,
            "slots": slots,
            "shortfall": left,
        })

    return pace, tasks, free


def _task_summary(t: dict) -> dict:
    return {
        "deadline_id": t["deadline_id"],
        "task_name": t["task_name"],
        "due_date": t["due_date"],
        "priority": t["priority"],
        "category": t["category"],
        "hours_needed": t["hours_needed"],
        "hours_scheduled": round(t["hours_needed"] - t["shortfall"], 2),
        "shortfall": t["shortfall"],
    }


def build_plan(as_of_date: str = None) -> dict:
    """
    Builds a day-by-day work plan: which task to work on each day and for
    how many hours, so that the earliest deadlines are covered first.

    Args:
        as_of_date: ISO date string to plan from. Defaults to the real
                    current date. Useful for testing.

    Returns:
        dict with status, the daily schedule, a per-task summary (including
        any shortfall = hours that could not be scheduled before the due
        date), and how many logged free hours are left unused.
    """
    today, error = _resolve_today(as_of_date)
    if error:
        return error

    pace, tasks, free = _allocate(today)
    if not tasks:
        return {"status": "success", "message": "No pending deadlines.", "schedule": [], "tasks": []}

    by_day = {}
    for t in tasks:
        for day, hours in t["slots"].items():
            by_day.setdefault(day, []).append({
                "deadline_id": t["deadline_id"],
                "task_name": t["task_name"],
                "hours": hours,
            })

    schedule = [
        {"date": day, "total_hours": round(sum(w["hours"] for w in work), 2), "work": work}
        for day, work in sorted(by_day.items())
    ]

    return {
        "status": "success",
        "pace_multiplier_used": pace,
        "schedule": schedule,
        "tasks": [_task_summary(t) for t in tasks],
        "unscheduled_free_hours": round(sum(free.values()), 2),
    }


def get_negotiation_options(as_of_date: str = None) -> dict:
    """
    For every pending deadline that does NOT fit in the available time,
    lists the concrete ways out:
        - defer_lower_priority : push back a less important task that is
                                 using hours before this due date
        - request_extension    : the earliest new due date that would work,
                                 based on free hours logged after the due date
        - find_more_time       : how many extra free hours are needed
        - reduce_scope         : how much of the task fits in the time there is

    Args:
        as_of_date: ISO date string to calculate from. Defaults to today.

    Returns:
        dict with status and one entry per at-risk deadline, each carrying
        its shortfall and a list of options.
    """
    today, error = _resolve_today(as_of_date)
    if error:
        return error

    pace, tasks, free = _allocate(today)
    short_tasks = [t for t in tasks if t["shortfall"] > 0]
    if not short_tasks:
        return {
            "status": "success",
            "message": "All pending deadlines fit in the available time. Nothing to negotiate.",
            "negotiations": [],
        }

    negotiations = []
    deferral_claimed = {}  # deadline_id -> hours already promised to an earlier at-risk task
    for t in short_tasks:
        shortfall = t["shortfall"]
        due = t["due_date"]
        options = []

        # Option: defer a lower-priority task that holds hours before this due date
        donors = []
        for other in tasks:
            if PRIORITY_WEIGHT.get(other["priority"], 0) >= PRIORITY_WEIGHT.get(t["priority"], 0):
                continue
            hours_held = round(sum(h for day, h in other["slots"].items() if day <= due)
                               - deferral_claimed.get(other["deadline_id"], 0.0), 2)
            if hours_held > 0:
                donors.append({
                    "deadline_id": other["deadline_id"],
                    "task_name": other["task_name"],
                    "priority": other["priority"],
                    "hours_freed": hours_held,
                })
        if donors:
            hours_freed = round(sum(d["hours_freed"] for d in donors), 2)
            names = ", ".join(d["task_name"] for d in donors)
            options.append({
                "type": "defer_lower_priority",
                "description": f"Defer {names} to free {hours_freed}h before {due}.",
                "tasks_to_defer": donors,
                "hours_freed": hours_freed,
                "covers_shortfall": hours_freed >= shortfall,
            })
            # Same rule as the extension below: hours are only claimed if they fully
            # cover the shortfall, so two at-risk tasks are never promised the same hours.
            if hours_freed >= shortfall:
                to_claim = shortfall
                for d in donors:
                    claim = min(d["hours_freed"], to_claim)
                    deferral_claimed[d["deadline_id"]] = deferral_claimed.get(d["deadline_id"], 0.0) + claim
                    to_claim = round(to_claim - claim, 2)

        # Option: ask for an extension, using free hours logged after the due date.
        # Hours are only claimed if they fully cover the shortfall, so two at-risk
        # tasks are never promised the same later hours.
        left = shortfall
        claimed = {}
        new_due = None
        for day in sorted(free):
            if day <= due or free[day] <= 0:
                continue
            take = min(free[day], left)
            claimed[day] = take
            left = round(left - take, 2)
            if left <= 0:
                new_due = day
                break
        if new_due:
            for day, hours in claimed.items():
                free[day] = round(free[day] - hours, 2)
            days_extended = (date.fromisoformat(new_due) - date.fromisoformat(due)).days
            options.append({
                "type": "request_extension",
                "description": f"Ask to move the due date to {new_due} ({days_extended} day(s) later).",
                "new_due_date": new_due,
                "days_extended": days_extended,
            })
        else:
            options.append({
                "type": "request_extension",
                "description": f"An extension only helps if {left}h more free time is logged after {due}.",
                "new_due_date": None,
                "hours_still_uncovered": left,
            })

        # Option: find more free time before the due date
        options.append({
            "type": "find_more_time",
            "description": f"Free up {shortfall}h more on or before {due}.",
            "extra_hours_needed": shortfall,
        })

        # Option: hand in a reduced scope
        hours_that_fit = round(t["hours_needed"] - shortfall, 2)
        percent = round(100 * hours_that_fit / t["hours_needed"]) if t["hours_needed"] else 0
        options.append({
            "type": "reduce_scope",
            "description": f"Only about {percent}% of the work fits ({hours_that_fit}h of {t['hours_needed']}h).",
            "hours_that_fit": hours_that_fit,
            "percent_of_task": percent,
        })

        negotiations.append({**_task_summary(t), "options": options})

    return {
        "status": "success",
        "pace_multiplier_used": pace,
        "negotiations": negotiations,
    }


def log_recommendation(deadline_id: int, recommendation: str) -> dict:
    """
    Saves what the agent recommended for a deadline (history table), so it
    can later be compared with what actually happened.

    Args:
        deadline_id: the deadline the recommendation is about
        recommendation: short text of what was recommended
    """
    try:
        deadline_id = int(deadline_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": "deadline_id must be an integer."}

    if not recommendation or not recommendation.strip():
        return {"status": "error", "message": "recommendation cannot be empty."}

    matching = next((d for d in storage.get_deadlines() if d["deadline_id"] == deadline_id), None)
    if not matching:
        return {"status": "error", "message": f"No deadline found with id {deadline_id}."}

    recommendation = recommendation.strip()

    # Asking the same question twice should not log the same advice twice
    earlier = [h for h in storage.get_history()
               if h["deadline_id"] == deadline_id and h["outcome"] == "unknown"]
    if earlier and max(earlier, key=lambda h: h["history_id"])["recommendation"] == recommendation:
        return {
            "status": "success",
            "message": f"That recommendation for '{matching['task_name']}' is already logged.",
        }

    storage.add_history_record(recommendation, deadline_id=deadline_id)
    return {
        "status": "success",
        "message": f"Logged recommendation for '{matching['task_name']}'.",
    }


# ---------------------------------------------------------------------
# Tool schemas (for LLM function-calling in Module 6 - Agent Orchestration)
# ---------------------------------------------------------------------
_AS_OF_DATE_PROPERTY = {
    "as_of_date": {
        "type": "string",
        "description": "Date to calculate from, YYYY-MM-DD (optional, defaults to today)",
    },
}

BUILD_PLAN_SCHEMA = {
    "name": "build_plan",
    "description": "Build a day-by-day work plan that assigns the user's free hours to "
                    "pending deadlines, earliest due date first. Use this when the user asks "
                    "what to work on each day or wants a schedule.",
    "input_schema": {"type": "object", "properties": _AS_OF_DATE_PROPERTY, "required": []},
}

GET_NEGOTIATION_OPTIONS_SCHEMA = {
    "name": "get_negotiation_options",
    "description": "For each deadline that does not fit in the available time, list the ways "
                    "out: defer a lower-priority task, request an extension (with the earliest "
                    "workable new date), find more free time, or reduce scope. Use this when a "
                    "deadline is at risk and the user needs to decide what to do about it.",
    "input_schema": {"type": "object", "properties": _AS_OF_DATE_PROPERTY, "required": []},
}

LOG_RECOMMENDATION_SCHEMA = {
    "name": "log_recommendation",
    "description": "Save the recommendation you gave the user for a specific deadline, so it "
                    "can later be compared with the real outcome.",
    "input_schema": {
        "type": "object",
        "properties": {
            "deadline_id": {"type": "integer", "description": "ID of the deadline the recommendation is about"},
            "recommendation": {"type": "string", "description": "Short summary of what you recommended"},
        },
        "required": ["deadline_id", "recommendation"],
    },
}


# ---------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    storage.init_db()
    storage.reset_db()

    import json
    import deadline_tool as dt
    import availability_tool as at

    # dates are relative to today so the self-test never goes stale
    def days_from_now(n):
        return (date.today() + timedelta(days=n)).isoformat()

    # A low-priority task due first is eating hours the high-priority one needs
    dt.add_deadline("Club Poster", days_from_now(1), estimated_hours=2, priority="low")
    dt.add_deadline("DBMS Assignment", days_from_now(3), estimated_hours=5, priority="high")
    dt.add_deadline("Easy Quiz", days_from_now(7), estimated_hours=1, priority="medium")

    at.set_availability(days_from_now(0), 2)
    at.set_availability(days_from_now(1), 2)
    at.set_availability(days_from_now(2), 1)
    at.set_availability(days_from_now(3), 2)
    at.set_availability(days_from_now(5), 3)

    # Simulate memory: user historically needs 1.5x their estimate
    storage.set_memory("pace_multiplier", "1.5")

    print("Day-by-day plan:")
    print(json.dumps(build_plan(), indent=2))

    print("\nNegotiation options:")
    print(json.dumps(get_negotiation_options(), indent=2))

    print("\nLogging a recommendation:")
    print(log_recommendation(2, "Defer Club Poster and find 0.5h more for DBMS Assignment."))
    print(log_recommendation(999, "No such deadline."))
    print("History:", storage.get_history())
