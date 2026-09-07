"""
Module 4: Reprioritization Tool
-----------------------------------
This is "Tool 3" of the agent's 3 tools.

Purpose: combine deadline data (Module 2) and availability data (Module 3)
to answer the real question: "given how much time is actually left, which
deadlines are at risk of being missed?"

This is NOT just a formula that always runs the same way — the agent
(Module 6) decides WHEN to call this (e.g. only when the user asks
something like "what should I focus on?"), and combines its output with
memory (pace_multiplier) to reason about priority. This module just does
the deterministic feasibility math; the judgment/reasoning layer sits on
top of it in Module 6/7.
"""

from datetime import date
import storage

# Priority weight used to break ties when multiple deadlines are at risk
PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def check_feasibility(as_of_date: str = None) -> dict:
    """
    Checks every pending deadline against the time actually available
    before its due date, adjusted by the user's learned pace (memory).

    Args:
        as_of_date: ISO date string to calculate "today" from. Defaults
                    to the real current date. Useful for testing.

    Returns:
        dict with status, and a list of deadlines each annotated with:
            - hours_needed (estimated_hours * pace_multiplier)
            - hours_available (sum of availability up to due_date)
            - feasible (bool)
            - risk_level ("safe" | "tight" | "at_risk")
        Sorted so the most urgent/at-risk deadlines come first.
    """
    today = as_of_date or date.today().isoformat()

    try:
        date.fromisoformat(today)
    except ValueError:
        return {"status": "error", "message": "as_of_date must be in YYYY-MM-DD format."}

    pending = storage.get_deadlines(status="pending")
    if not pending:
        return {"status": "success", "message": "No pending deadlines.", "results": []}

    # Learned pace multiplier from memory (defaults to 1.0 = trust the estimate as-is)
    pace_raw = storage.get_memory("pace_multiplier")
    pace_multiplier = float(pace_raw) if pace_raw else 1.0

    results = []
    for d in pending:
        due = d["due_date"]

        # only count availability from today up to (and including) the due date
        avail_records = storage.get_availability(today, due)
        hours_available = sum(r["available_hours"] for r in avail_records)

        hours_needed = round(d["estimated_hours"] * pace_multiplier, 2)

        feasible = hours_available >= hours_needed

        if not feasible:
            risk_level = "at_risk"
        elif hours_available - hours_needed <= hours_needed * 0.2:
            # less than 20% buffer left over -> cutting it close
            risk_level = "tight"
        else:
            risk_level = "safe"

        results.append({
            "deadline_id": d["deadline_id"],
            "task_name": d["task_name"],
            "due_date": due,
            "priority": d["priority"],
            "estimated_hours": d["estimated_hours"],
            "hours_needed_with_pace": hours_needed,
            "hours_available_before_due": hours_available,
            "feasible": feasible,
            "risk_level": risk_level,
        })

    # Sort: at_risk first, then tight, then safe; within same risk, higher priority first,
    # then earlier due date first
    risk_order = {"at_risk": 0, "tight": 1, "safe": 2}
    results.sort(key=lambda r: (
        risk_order[r["risk_level"]],
        -PRIORITY_WEIGHT.get(r["priority"], 0),
        r["due_date"],
    ))

    at_risk = [r["task_name"] for r in results if r["risk_level"] == "at_risk"]

    return {
        "status": "success",
        "pace_multiplier_used": pace_multiplier,
        "results": results,
        "at_risk_tasks": at_risk,
    }


# ---------------------------------------------------------------------
# Tool schema (for LLM function-calling in Module 6 - Agent Orchestration)
# ---------------------------------------------------------------------
TOOL_SCHEMA = {
    "name": "check_feasibility",
    "description": "Check every pending deadline against actual available hours "
                    "(adjusted for the user's known work pace) to determine which "
                    "deadlines are safe, tight, or at risk of being missed. "
                    "Use this when the user asks what to prioritize or focus on.",
    "input_schema": {
        "type": "object",
        "properties": {
            "as_of_date": {
                "type": "string",
                "description": "Date to calculate from, YYYY-MM-DD (optional, defaults to today)",
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    storage.init_db()
    storage.reset_db()

    import deadline_tool as dt
    import availability_tool as at

    # Simulate a realistic squeeze: two deadlines, limited time
    dt.add_deadline("DBMS Assignment", "2026-09-08", estimated_hours=5, priority="high")
    dt.add_deadline("Presentation Prep", "2026-09-07", estimated_hours=3, priority="medium")
    dt.add_deadline("Easy Quiz", "2026-09-12", estimated_hours=1, priority="low")

    at.set_availability("2026-09-05", 2)
    at.set_availability("2026-09-06", 2)
    at.set_availability("2026-09-07", 1)
    at.set_availability("2026-09-08", 2)

    # Simulate memory: user historically needs 1.5x their estimate
    storage.set_memory("pace_multiplier", "1.5")

    result = check_feasibility(as_of_date="2026-09-05")

    import json
    print(json.dumps(result, indent=2))

    print("\nAt-risk tasks:", result.get("at_risk_tasks"))