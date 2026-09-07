"""
Module 3: Availability Tool
------------------------------
This is "Tool 2" of the agent's 3 tools.

Purpose: let the user log how many free hours they have on a given day,
and query availability over a date range. This is the entry point for
all time-availability data — the Reprioritization Tool (Module 4) and
Agent Orchestration (Module 6) read whatever this tool writes.

Design note: same pattern as Module 2 — validation lives HERE, storage.py
just persists whatever it's given.
"""

from datetime import date
import storage


def set_availability(day: str, available_hours: float) -> dict:
    """
    Logs (or updates) how many free hours the user has on a given date.

    Args:
        day: ISO date string (YYYY-MM-DD)
        available_hours: number of free hours that day (0-24)

    Returns:
        dict with status ("success" or "error") and a message.
    """
    try:
        date.fromisoformat(day)
    except (ValueError, TypeError):
        return {"status": "error", "message": "day must be in YYYY-MM-DD format."}

    try:
        available_hours = float(available_hours)
    except (ValueError, TypeError):
        return {"status": "error", "message": "available_hours must be a number."}

    if not (0 <= available_hours <= 24):
        return {"status": "error", "message": "available_hours must be between 0 and 24."}

    storage.set_availability(day, available_hours)

    return {
        "status": "success",
        "message": f"Set availability for {day}: {available_hours}h free."
    }


def get_availability(start_date: str = None, end_date: str = None) -> dict:
    """
    Fetches availability, optionally within a date range (inclusive).

    Args:
        start_date: ISO date string, start of range (optional)
        end_date: ISO date string, end of range (optional)

    Returns:
        dict with status, list of availability entries, and total hours.
    """
    if start_date:
        try:
            date.fromisoformat(start_date)
        except ValueError:
            return {"status": "error", "message": "start_date must be in YYYY-MM-DD format."}

    if end_date:
        try:
            date.fromisoformat(end_date)
        except ValueError:
            return {"status": "error", "message": "end_date must be in YYYY-MM-DD format."}

    if start_date and end_date and start_date > end_date:
        return {"status": "error", "message": "start_date cannot be after end_date."}

    records = storage.get_availability(start_date, end_date)
    total_hours = sum(r["available_hours"] for r in records)

    return {
        "status": "success",
        "availability": records,
        "total_available_hours": total_hours,
    }


# ---------------------------------------------------------------------
# Tool schemas (for LLM function-calling in Module 6 - Agent Orchestration)
# ---------------------------------------------------------------------
SET_AVAILABILITY_SCHEMA = {
    "name": "set_availability",
    "description": "Log how many free hours the user has available on a specific date.",
    "input_schema": {
        "type": "object",
        "properties": {
            "day": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            "available_hours": {"type": "number", "description": "Free hours available that day (0-24)"},
        },
        "required": ["day", "available_hours"],
    },
}

GET_AVAILABILITY_SCHEMA = {
    "name": "get_availability",
    "description": "Retrieve the user's logged availability, optionally within a date range, "
                    "including the total free hours across that range.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start of range, YYYY-MM-DD (optional)"},
            "end_date": {"type": "string", "description": "End of range, YYYY-MM-DD (optional)"},
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

    # valid entries
    print(set_availability("2026-09-05", 2))
    print(set_availability("2026-09-06", 4))
    print(set_availability("2026-09-07", 3))

    # updating an existing date (should overwrite, not duplicate)
    print(set_availability("2026-09-05", 1.5))

    # invalid date format
    print(set_availability("05-09-2026", 3))

    # invalid hours (out of range)
    print(set_availability("2026-09-08", 30))

    print("\nAll availability:")
    print(get_availability())

    print("\nAvailability between 2026-09-06 and 2026-09-07:")
    print(get_availability("2026-09-06", "2026-09-07"))