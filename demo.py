"""
DEMO SCRIPT — Modules 1 to 5 and 7
------------------------------------
This is NOT a separate module. It's a walkthrough script that ties together:
    Module 1 (Storage), Module 2 (Deadline Tool), Module 3 (Availability Tool),
    Module 4 (Reprioritization Tool), Module 5 (Memory), Module 7 (Negotiation Tool)

Purpose: demonstrate to the tutor that the data layer + tools + memory
all work together correctly, WITHOUT the Agent Orchestration (Module 6)
on top. Module 6 lets an LLM decide when to call these tools
automatically — this script calls them in a clear, narrated sequence so
the logic itself can be verified and explained. It needs no API key.

Run this with: python demo.py
"""

import json
from datetime import date, timedelta
import storage
import deadline_tool as dt
import availability_tool as at
import reprioritization_tool as rt
import memory as mem
import negotiation_tool as nt


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def pretty(data):
    print(json.dumps(data, indent=2))


def days_from_now(n):
    """Dates are relative to today so the demo never goes stale."""
    return (date.today() + timedelta(days=n)).isoformat()


# =======================================================================
# STEP 0: Reset everything for a clean demo
# =======================================================================
section("STEP 0: Initialize & reset database")
storage.init_db()
storage.reset_db()


# =======================================================================
# STEP 1: Add deadlines (Module 2 - Deadline Tool)
# =======================================================================
section("STEP 1: Adding deadlines (Deadline Tool)")

print(dt.add_deadline("DBMS Assignment", days_from_now(3), estimated_hours=5, priority="high"))
print(dt.add_deadline("Presentation Prep", days_from_now(2), estimated_hours=3, priority="medium"))
print(dt.add_deadline("Easy Quiz", days_from_now(7), estimated_hours=1, priority="low"))

print("\nCurrent pending deadlines:")
pretty(dt.get_deadlines("pending"))


# =======================================================================
# STEP 2: Log availability (Module 3 - Availability Tool)
# =======================================================================
section("STEP 2: Logging available free hours (Availability Tool)")

print(at.set_availability(days_from_now(0), 2))
print(at.set_availability(days_from_now(1), 2))
print(at.set_availability(days_from_now(2), 1))
print(at.set_availability(days_from_now(3), 2))

print("\nAll logged availability:")
pretty(at.get_availability())


# =======================================================================
# STEP 3: Simulate learned memory (Module 5 - Memory)
# =======================================================================
section("STEP 3: Simulating a past outcome to build memory")

# Pretend the user just finished a past task that took longer than estimated.
# This will update the pace_multiplier BEFORE we check feasibility, so the
# feasibility check below reflects a realistic, personalized estimate.
storage.set_memory("pace_multiplier", "1.5")
print("Manually seeded pace_multiplier = 1.5 (user historically takes 1.5x their estimate)")

print("\nReliability summary so far:")
pretty(mem.get_reliability_summary())


# =======================================================================
# STEP 4: Run feasibility check (Module 4 - Reprioritization Tool)
# =======================================================================
section("STEP 4: Checking feasibility of all deadlines (Reprioritization Tool)")

result = rt.check_feasibility()
pretty(result)

print("\n>>> AT-RISK TASKS:", result.get("at_risk_tasks"))


# =======================================================================
# STEP 5: Simulate finishing a task and recording the real outcome
# =======================================================================
section("STEP 5: Recording an outcome after finishing a task (Memory learns)")

print("Before recording outcome, pace_multiplier =", mem.get_pace_multiplier())

# Estimated 3h but it really took 6h -> a 2.0x ratio, which pulls the pace above 1.5
outcome_result = mem.record_outcome(deadline_id=2, actual_hours_taken=6, outcome="missed")
print(outcome_result)

print("After recording outcome, pace_multiplier =", mem.get_pace_multiplier())

print("\nUpdated reliability summary:")
pretty(mem.get_reliability_summary())


# =======================================================================
# STEP 6: Re-run feasibility check with updated memory
# =======================================================================
section("STEP 6: Re-checking feasibility with the NEWLY LEARNED pace")

result2 = rt.check_feasibility()
pretty(result2)

print("\n>>> AT-RISK TASKS (after learning):", result2.get("at_risk_tasks"))

# =======================================================================
# STEP 7: Plan the remaining work and list the ways out (Module 7 - Negotiation Tool)
# =======================================================================
section("STEP 7: Day-by-day plan and negotiation options (Negotiation Tool)")

print("Day-by-day plan:")
pretty(nt.build_plan())

print("\nOptions for each deadline that doesn't fit:")
pretty(nt.get_negotiation_options())

section("DEMO COMPLETE")
print("This demonstrates: Storage -> Deadline Tool -> Availability Tool ->")
print("Reprioritization Tool -> Memory -> Negotiation Tool, all working together")
print("WITHOUT the Agent Orchestration layer. Module 6 (agent.py) lets an LLM")
print("decide when to call each of these automatically based on natural conversation.")