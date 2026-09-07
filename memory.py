"""
Module 5: Memory Module
--------------------------
Purpose: this is what makes the agent feel "personalized" over time instead
of treating every session like a stranger. It learns facts about the user
from their actual history and makes those facts available to the
Reprioritization Tool (Module 4) and the Agent Orchestration layer (Module 6).

Two kinds of memory here:
1. Key-value facts (stored in storage.memory table) — e.g. pace_multiplier
2. Derived insights computed from storage.history — e.g. "usually misses
   presentation-type deadlines"

This module does NOT decide what to DO with these facts (that's the agent's
job in Module 6/7) — it only maintains and surfaces them.
"""

from datetime import date
import storage

DEFAULT_PACE_MULTIPLIER = 1.0


# ---------------------------------------------------------------------
# Recording outcomes (called after a deadline is marked done/missed)
# ---------------------------------------------------------------------
def record_outcome(deadline_id: int, actual_hours_taken: float, outcome: str) -> dict:
    """
    Call this once a deadline is finished (or missed) to teach the agent
    something about the user's real pace and reliability.

    Args:
        deadline_id: the deadline this outcome refers to
        actual_hours_taken: how many hours it actually took (user-reported)
        outcome: 'met' or 'missed'

    Returns:
        dict with status and a message, including the updated pace_multiplier.
    """
    if outcome not in ("met", "missed"):
        return {"status": "error", "message": "outcome must be 'met' or 'missed'."}

    try:
        actual_hours_taken = float(actual_hours_taken)
    except (ValueError, TypeError):
        return {"status": "error", "message": "actual_hours_taken must be a number."}

    deadlines = storage.get_deadlines()
    matching = next((d for d in deadlines if d["deadline_id"] == deadline_id), None)
    if not matching:
        return {"status": "error", "message": f"No deadline found with id {deadline_id}."}

    estimated = matching["estimated_hours"]

    # Update pace_multiplier as a rolling average with the new data point.
    # Simple approach: blend old pace with this task's actual/estimated ratio.
    if estimated > 0:
        this_task_ratio = actual_hours_taken / estimated
        old_pace = get_pace_multiplier()
        # weight new data at 30% so one outlier task doesn't swing it wildly
        new_pace = round((old_pace * 0.7) + (this_task_ratio * 0.3), 2)
        storage.set_memory("pace_multiplier", str(new_pace))
    else:
        new_pace = get_pace_multiplier()

    # Log this as history so we can later analyze patterns (e.g. always misses "coding" tasks)
    recommendation_note = f"Outcome recorded: {outcome}, actual={actual_hours_taken}h vs estimated={estimated}h"
    storage.add_history_record(recommendation_note, deadline_id=deadline_id, outcome=outcome)

    # Also update the deadline's own status to keep things in sync
    storage.update_deadline_status(deadline_id, "done" if outcome == "met" else "missed")

    return {
        "status": "success",
        "message": f"Recorded outcome for '{matching['task_name']}': {outcome}.",
        "updated_pace_multiplier": new_pace,
    }


# ---------------------------------------------------------------------
# Reading memory
# ---------------------------------------------------------------------
def get_pace_multiplier() -> float:
    """Returns the learned pace multiplier, or the default if none learned yet."""
    raw = storage.get_memory("pace_multiplier")
    return float(raw) if raw else DEFAULT_PACE_MULTIPLIER


def get_reliability_summary() -> dict:
    """
    Looks at past history to summarize how often the user meets vs misses
    deadlines. Useful context for the agent when reasoning about risk.
    """
    history = storage.get_history()
    outcomes = [h["outcome"] for h in history if h["outcome"] in ("met", "missed")]

    if not outcomes:
        return {
            "status": "success",
            "total_tracked": 0,
            "met_count": 0,
            "missed_count": 0,
            "missed_rate": None,
            "pace_multiplier": get_pace_multiplier(),
        }

    met_count = outcomes.count("met")
    missed_count = outcomes.count("missed")
    total = len(outcomes)

    return {
        "status": "success",
        "total_tracked": total,
        "met_count": met_count,
        "missed_count": missed_count,
        "missed_rate": round(missed_count / total, 2),
        "pace_multiplier": get_pace_multiplier(),
    }


def get_all_memory() -> dict:
    """Returns every key-value fact currently stored in memory, plus a reliability summary."""
    facts = storage.get_memory()
    summary = get_reliability_summary()
    return {"status": "success", "facts": facts, "reliability_summary": summary}


# ---------------------------------------------------------------------
# Tool schema (for LLM function-calling in Module 6 - Agent Orchestration)
# ---------------------------------------------------------------------
RECORD_OUTCOME_SCHEMA = {
    "name": "record_outcome",
    "description": "Record whether a deadline was met or missed, and how many hours it "
                    "actually took. This teaches the agent the user's real work pace "
                    "for better future predictions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "deadline_id": {"type": "integer", "description": "ID of the deadline being closed out"},
            "actual_hours_taken": {"type": "number", "description": "How many hours it actually took"},
            "outcome": {"type": "string", "description": "Whether the deadline was met or missed", "enum": ["met", "missed"]},
        },
        "required": ["deadline_id", "actual_hours_taken", "outcome"],
    },
}

GET_MEMORY_SCHEMA = {
    "name": "get_all_memory",
    "description": "Retrieve everything the agent has learned about the user so far: "
                    "their pace multiplier and their deadline-reliability history "
                    "(how often they meet vs miss deadlines).",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


# ---------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    storage.init_db()
    storage.reset_db()

    import deadline_tool as dt
    dt.add_deadline("DBMS Assignment", "2026-09-10", estimated_hours=5, priority="high")
    dt.add_deadline("Presentation Prep", "2026-09-08", estimated_hours=3, priority="medium")

    print("Starting pace multiplier:", get_pace_multiplier())

    # Simulate: DBMS Assignment estimated at 5h but actually took 8h -> user underestimates
    print(record_outcome(deadline_id=1, actual_hours_taken=8, outcome="met"))
    print("Pace multiplier after 1st outcome:", get_pace_multiplier())

    # Simulate: Presentation Prep estimated at 3h, took 4.5h, and was missed anyway (ran out of time)
    print(record_outcome(deadline_id=2, actual_hours_taken=4.5, outcome="missed"))
    print("Pace multiplier after 2nd outcome:", get_pace_multiplier())

    import json
    print("\nReliability summary:")
    print(json.dumps(get_reliability_summary(), indent=2))

    print("\nAll memory:")
    print(json.dumps(get_all_memory(), indent=2))