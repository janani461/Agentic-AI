"""
Module 6b: Rule-Based Agent
------------------------------
This is the agent that runs when NO API key is set. It does the same job
as the Gemini agent in agent.py — read a message, decide which tool(s) to
call, combine the results into an answer — but the "deciding" is done by
plain Python rules instead of a language model.

How it decides:
    1. Intent  : keyword patterns work out what the user wants
                 (add a deadline, log free hours, "what should I focus on?", ...)
    2. Details : small parsers pull out dates ("Friday", "tomorrow",
                 "15 Oct"), hours ("5 hours") and priority from the text
    3. Tools   : the matching tool(s) from Modules 2-5 and 7 are called
    4. Judgment: for an at-risk deadline, a fixed set of rules picks ONE
                 negotiation option to recommend, and the choice is logged

Trade-off: it only understands the kinds of message it has rules for.
Anything else gets a reply listing what it can do. Set GEMINI_API_KEY to
switch to the language-model agent, which handles free-form questions.
"""

import re
from datetime import date, timedelta

import deadline_tool as dt
import availability_tool as at
import reprioritization_tool as rt
import memory as mem
import negotiation_tool as nt

RISK_ICON = {"at_risk": "🔴", "tight": "🟡", "safe": "🟢"}
RISK_LABEL = {"at_risk": "At risk.", "tight": "Tight.", "safe": "On track."}

HELP_TEXT = """I can help with these (I'm running on built-in rules, so phrase it roughly like the examples):

- **Add a deadline:** "Add DBMS assignment due Friday, 5 hours, high priority"
- **Log free time:** "I'm free 3 hours tomorrow"
- **Check where you stand:** "What should I focus on?"
- **Get a schedule:** "Give me a plan"
- **See your options:** "What are my options?"
- **Close out a task:** "I finished the DBMS assignment, it took 6 hours"
- **Look things up:** "Show my deadlines", "Show my free hours", "What have you learned about me?"
"""


# ---------------------------------------------------------------------
# Parsers: pull dates, hours, priority and category out of free text
# ---------------------------------------------------------------------
WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thurs": 3, "thur": 3, "thu": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

_MONTH = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_WEEKDAY = "(" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + ")"
_RELATIVE_DAYS = (
    (r"\bday after tomorrow\b", 2),
    (r"\btomorrow\b", 1),
    (r"\b(?:today|tonight)\b", 0),
    (r"\b(?:next week|in a week)\b", 7),
)
HOURS_PATTERN = r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b"


def parse_date(text: str, today: date = None):
    """
    Finds the first date mentioned in the text.

    Understands: 2026-10-15, today, tomorrow, day after tomorrow, next week,
    "in 3 days", "15 Oct" / "October 15th", and weekday names ("Friday").

    Returns:
        (iso_date, (start, end)) where start/end locate the date words in
        the text, or (None, None) if no date was found.
    """
    today = today or date.today()
    lower = text.lower()

    m = re.search(r"\b\d{4}-\d{2}-\d{2}\b", lower)
    if m:
        try:
            date.fromisoformat(m.group())
            return m.group(), m.span()
        except ValueError:
            pass

    for pattern, days in _RELATIVE_DAYS:
        m = re.search(pattern, lower)
        if m:
            return (today + timedelta(days=days)).isoformat(), m.span()

    m = re.search(r"\bin (\d+) days?\b", lower)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat(), m.span()

    # "15 Oct" / "15th of October", then "Oct 15"
    for pattern, day_group, month_group in (
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}\b", 1, 2),
        (rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", 2, 1),
    ):
        m = re.search(pattern, lower)
        if m:
            day, month = int(m.group(day_group)), MONTHS[m.group(month_group)[:3]]
            try:
                parsed = date(today.year, month, day)
                if parsed < today:  # "5 Jan" said in October means next January
                    parsed = date(today.year + 1, month, day)
                return parsed.isoformat(), m.span()
            except ValueError:
                pass

    m = re.search(rf"\b(?:(next|this)\s+)?{_WEEKDAY}\b", lower)
    if m:
        days_ahead = (WEEKDAYS[m.group(2)] - today.weekday()) % 7
        if days_ahead == 0 and m.group(1) == "next":
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).isoformat(), m.span()

    return None, None


def parse_hours(text: str):
    """Returns the first number of hours mentioned ("5 hours", "2.5h", "an hour"), or None."""
    m = re.search(HOURS_PATTERN, text.lower())
    if m:
        return float(m.group(1))
    if re.search(r"\ban hour\b", text.lower()):
        return 1.0
    return None


def parse_priority(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(high|urgent|important|top)\b", lower):
        return "high"
    if re.search(r"\blow\b", lower):
        return "low"
    return "medium"


def parse_category(text: str) -> str:
    lower = text.lower()
    for category, words in (
        ("exam", r"\b(exam|test|quiz|midterm|viva)\b"),
        ("presentation", r"\b(presentation|talk|seminar|demo)\b"),
        ("project", r"\bproject\b"),
        ("assignment", r"\b(assignment|homework|lab|report|essay)\b"),
    ):
        if re.search(words, lower):
            return category
    return "other"


_NAME_LEAD = re.compile(
    r"^\s*(?:please\s+|can you\s+|could you\s+)?"
    r"(?:(?:add|create|make)\s+|i\s+have\s+|i'?ve\s+got\s+)?"
    r"(?:(?:a|an|my|the|another)\s+)?(?:new\s+)?"
    r"(?:(?:deadline|task)\s*(?:for|called|named|:)?\s+)?"
    r"(?:(?:a|an|my|the)\s+)?",
    re.IGNORECASE,
)
# The task name ends where the details start
_NAME_END = re.compile(
    r"\bdue\b|[,;(]|" + HOURS_PATTERN + r"|\b(?:high|medium|low|top)\s+priority\b|"
    r"\b(?:priority|estimated|est|takes?|needs?|will take|urgent)\b",
    re.IGNORECASE,
)


def parse_task_name(message: str, date_span) -> str:
    """Pulls the task name out of an "add a deadline" message. Text in double quotes wins."""
    quoted = re.search(r'["“]([^"”]{2,})["”]', message)
    if quoted:
        return quoted.group(1).strip()

    # the date can come first, as in "Tomorrow I have a physics exam"
    if date_span and not message[:date_span[0]].strip(" ,"):
        message, date_span = message[date_span[1]:].lstrip(" ,"), None

    start = _NAME_LEAD.match(message).end()
    # so can the estimate, as in "a 5 hour DBMS assignment"
    hours_first = re.match(HOURS_PATTERN + r"\s*", message[start:], re.IGNORECASE)
    if hours_first:
        start += hours_first.end()
    rest = message[start:]

    end = len(rest)
    m = _NAME_END.search(rest)
    if m:
        end = m.start()
    if date_span and date_span[0] >= start:
        end = min(end, date_span[0] - start)

    name = rest[:end]
    # drop the joining words left behind, as in "physics exam on [Friday]" or "essay that [takes 3 hours]"
    name = re.sub(r"(?:\s+(?:on|for|at|in|by|this|next|is|it|around|about|that|which))+\s*$", "", name,
                  flags=re.IGNORECASE)
    return name.strip(" .:-")


def find_deadline(message: str, deadlines: list):
    """
    Works out which deadline a message is talking about, by id ("#3") or
    by the words of its name.

    Returns:
        (deadline, None) on a clear match, or (None, candidates) where
        candidates is empty (nothing matched) or several (ambiguous).
    """
    lower = message.lower()

    m = re.search(r"(?:#|\bdeadline\s+|\bid\s+)(\d+)\b", lower)
    if m:
        match = next((d for d in deadlines if d["deadline_id"] == int(m.group(1))), None)
        return (match, None) if match else (None, [])

    def score(d):
        name = d["task_name"].lower()
        if name in lower:
            return 100 + len(name)
        words = [w for w in re.findall(r"[a-z0-9]+", name) if len(w) >= 3]
        return sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", lower))

    # a task that is still pending is the likelier one to be closing out
    for pool in ([d for d in deadlines if d["status"] == "pending"], deadlines):
        scored = [(score(d), d) for d in pool]
        best = max((s for s, _ in scored), default=0)
        if best > 0:
            top = [d for s, d in scored if s == best]
            return (top[0], None) if len(top) == 1 else (None, top)

    return None, []


# ---------------------------------------------------------------------
# Tool calling: every call goes through here so it can be shown and logged
# ---------------------------------------------------------------------
def say(text: str):
    """print() that survives a console or redirected file that cannot encode emoji (cp1252 on Windows)."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


class _Turn:
    """Collects the tool calls made while answering one message."""

    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.tool_calls = []

    def call(self, func, **tool_input):
        if self.verbose:
            say(f"   🔧 Agent is calling: {func.__name__}({tool_input})")
        result = func(**tool_input)
        if self.verbose:
            say(f"      -> {result}")
        self.tool_calls.append({"name": func.__name__, "input": tool_input})
        return result


# ---------------------------------------------------------------------
# Judgment: which negotiation option to recommend
# ---------------------------------------------------------------------
SHORT_EXTENSION_DAYS = 3     # an extension this short is easy to ask for
SMALL_GAP_PERCENT = 75       # if this much of the work fits, the gap is small
WORKABLE_SCOPE_PERCENT = 50  # below this, a reduced scope is not worth handing in


def recommend(item: dict, weak_spots: list) -> str:
    """
    Picks ONE option for a deadline that doesn't fit, and says why.

    Rules, in order (the first that applies wins):
        1. Deferring a lower-priority task covers the gap    -> defer it
        2. A short extension works with hours already logged -> ask for it
        3. Most of the work already fits                     -> find the few hours
        4. A longer extension works                          -> ask for it
        5. Deferring helps but is not enough                 -> defer and find the rest
        6. At least half the work fits                       -> reduce the scope
        7. Otherwise                                         -> ask for an extension
    """
    options = {o["type"]: o for o in item["options"]}
    defer = options.get("defer_lower_priority")
    extension = options["request_extension"]
    percent = options["reduce_scope"]["percent_of_task"]
    short, due = item["shortfall"], item["due_date"]

    if defer:
        names = " and ".join(t["task_name"] for t in defer["tasks_to_defer"])

    if defer and defer["covers_shortfall"]:
        text = (f"Defer {names}. That frees {defer['hours_freed']}h, which covers the {short}h gap, "
                f"and it is lower priority than this {item['priority']}-priority task.")
    elif extension["new_due_date"] and extension["days_extended"] <= SHORT_EXTENSION_DAYS:
        text = (f"Ask to move the due date to {extension['new_due_date']} "
                f"({extension['days_extended']} day(s) later). It is a short extension and you "
                f"already have free hours logged to cover it.")
    elif percent >= SMALL_GAP_PERCENT:
        text = (f"Find {short}h more on or before {due}. About {percent}% of the work already "
                f"fits, so the gap is small.")
    elif extension["new_due_date"]:
        text = (f"Ask to move the due date to {extension['new_due_date']} "
                f"({extension['days_extended']} days later). Only about {percent}% of the work "
                f"fits before {due}, and that is the earliest date your logged free hours cover it.")
    elif defer:
        remaining = round(short - defer["hours_freed"], 2)
        text = (f"Defer {names} to free {defer['hours_freed']}h, then find {remaining}h more "
                f"on or before {due}.")
    elif percent >= WORKABLE_SCOPE_PERCENT:
        text = (f"Agree a reduced scope. About {percent}% of the work fits, and you have no free "
                f"hours logged after {due} for an extension to use.")
    else:
        text = (f"Ask for an extension now, and log your free hours after {due} so I can say how "
                f"long you need. Only about {percent}% of the work fits, so finding time or "
                f"cutting scope will not be enough.")

    if item.get("category") in weak_spots:
        text += f" You have a history of missing {item['category']} deadlines, so act on this early."
    return text


# ---------------------------------------------------------------------
# Intents: one function per kind of request
# ---------------------------------------------------------------------
def _add_deadline(turn: _Turn, message: str) -> str:
    due_date, date_span = parse_date(message)
    hours = parse_hours(message)
    name = parse_task_name(message, date_span)

    missing = [label for label, value in (("a name", name), ("a due date", due_date),
                                          ("an estimate in hours", hours)) if not value]
    if missing:
        return (f"To add a deadline I still need {' and '.join(missing)}. "
                f'For example: "Add DBMS assignment due Friday, 5 hours, high priority".')

    result = turn.call(dt.add_deadline, task_name=name, due_date=due_date, estimated_hours=hours,
                       priority=parse_priority(message), category=parse_category(message))
    if result["status"] != "success":
        return f"I couldn't add that: {result['message']}"
    return f"{result['message']} Ask \"What should I focus on?\" to see whether it fits."


def _set_availability(turn: _Turn, message: str) -> str:
    hours = parse_hours(message)
    day, _ = parse_date(message)
    day = day or date.today().isoformat()

    result = turn.call(at.set_availability, day=day, available_hours=hours)
    if result["status"] != "success":
        return f"I couldn't log that: {result['message']}"
    return result["message"]


def _record_outcome(turn: _Turn, message: str) -> str:
    deadlines = turn.call(dt.get_deadlines)["deadlines"]
    match, candidates = find_deadline(message, deadlines)

    if not match:
        if candidates:
            listing = ", ".join(f"#{d['deadline_id']} {d['task_name']}" for d in candidates)
            return f"Which one do you mean: {listing}? Say it again with the number, like \"#{candidates[0]['deadline_id']}\"."
        return "I couldn't tell which deadline you mean. Say \"Show my deadlines\" to see their names and numbers."

    hours = parse_hours(message)
    if hours is None:
        return (f"How many hours did '{match['task_name']}' actually take? Tell me in one message, "
                f"for example: \"I finished #{match['deadline_id']}, it took 6 hours\".")

    # "didn't" alone is not enough: "it didn't take long" is not a missed deadline
    missed = re.search(r"\b(missed|failed)\b|\b(didn'?t|did not|couldn'?t|could not)\s+(?:\w+\s+){0,2}?"
                       r"(finish|complete|submit|make|do|hand|get)\b", message.lower())
    result = turn.call(mem.record_outcome, deadline_id=match["deadline_id"],
                       actual_hours_taken=hours, outcome="missed" if missed else "met")
    if result["status"] != "success":
        return f"I couldn't record that: {result['message']}"

    return (f"{result['message']} It took {hours}h against an estimate of {match['estimated_hours']}h, "
            f"so your pace multiplier is now {result['updated_pace_multiplier']}x. "
            f"I'll use that for your other deadlines.")


def _negotiation_text(turn: _Turn, show_options: bool) -> str:
    """Options and one recommendation for each deadline that doesn't fit. Logs each recommendation."""
    negotiation = turn.call(nt.get_negotiation_options)
    if not negotiation["negotiations"]:
        return "All your pending deadlines fit in the time you have logged. There is nothing to negotiate."

    weak_spots = turn.call(mem.get_all_memory)["category_patterns"]["weak_spots"]

    lines = []
    for item in negotiation["negotiations"]:
        lines.append(f"**{item['task_name']}** (due {item['due_date']}) is short by {item['shortfall']}h.")
        if show_options:
            for option in item["options"]:
                lines.append(f"- {option['description']}")
        recommendation = recommend(item, weak_spots)
        lines.append(f"➡️ **Recommendation:** {recommendation}")
        lines.append("")
        turn.call(nt.log_recommendation, deadline_id=item["deadline_id"], recommendation=recommendation)

    return "\n".join(lines).rstrip()


def _negotiate(turn: _Turn, message: str) -> str:
    return _negotiation_text(turn, show_options=True)


def _focus(turn: _Turn, message: str) -> str:
    result = turn.call(rt.check_feasibility)
    if not result.get("results"):
        return "You have no pending deadlines. Add one and I'll check whether it fits."

    pace = result["pace_multiplier_used"]
    lines = [f"Using your pace of {pace}x (how long tasks really take you, compared with your estimates):", ""]
    for r in result["results"]:
        lines.append(f"- {RISK_ICON[r['risk_level']]} **{r['task_name']}** (due {r['due_date']}, "
                     f"{r['priority']} priority): needs {r['hours_needed_with_pace']}h, "
                     f"{r['hours_available_before_due']}h available. {RISK_LABEL[r['risk_level']]}")

    if not result["at_risk_tasks"]:
        first = min(result["results"], key=lambda r: (
            r["hours_available_before_due"] - r["hours_needed_with_pace"], r["due_date"]))
        lines += ["", f"Nothing is at risk. Start with **{first['task_name']}**, which has the least slack."]
        return "\n".join(lines)

    lines += ["", f"Focus first on **{result['at_risk_tasks'][0]}**.", "", _negotiation_text(turn, show_options=False)]
    return "\n".join(lines)


def _plan(turn: _Turn, message: str) -> str:
    plan = turn.call(nt.build_plan)
    if not plan.get("schedule"):
        return "There is nothing to plan yet. Add a pending deadline and log some free hours first."

    lines = [f"Here is your plan, earliest deadline first (pace {plan['pace_multiplier_used']}x):", ""]
    for day in plan["schedule"]:
        weekday = date.fromisoformat(day["date"]).strftime("%a")
        work = ", ".join(f"{w['task_name']} {w['hours']}h" for w in day["work"])
        lines.append(f"- **{day['date']} ({weekday}):** {work}")

    short = [t for t in plan["tasks"] if t["shortfall"] > 0]
    if short:
        lines.append("")
        for t in short:
            lines.append(f"⚠️ **{t['task_name']}** is still short by {t['shortfall']}h.")
        lines.append("Ask \"What are my options?\" to see the ways out.")
    elif plan["unscheduled_free_hours"] > 0:
        lines += ["", f"Everything fits, with {plan['unscheduled_free_hours']}h of free time to spare."]

    return "\n".join(lines)


def _memory(turn: _Turn, message: str) -> str:
    memory = turn.call(mem.get_all_memory)
    summary = memory["reliability_summary"]
    lines = [f"- **Pace multiplier:** {summary['pace_multiplier']}x. "
             f"Tasks take you about {summary['pace_multiplier']} times your estimate."]

    if summary["total_tracked"]:
        lines.append(f"- **Track record:** {summary['met_count']} met and {summary['missed_count']} missed "
                     f"out of {summary['total_tracked']} recorded deadlines.")
    else:
        lines.append("- **Track record:** nothing recorded yet. Tell me when you finish or miss a deadline.")

    weak_spots = memory["category_patterns"]["weak_spots"]
    if weak_spots:
        lines.append(f"- **Weak spot:** you tend to miss {', '.join(weak_spots)} deadlines.")

    return "\n".join(lines)


def _list_availability(turn: _Turn, message: str) -> str:
    today = date.today().isoformat()
    records = [r for r in turn.call(at.get_availability)["availability"] if r["date"] >= today]
    if not records:
        return "You have no free hours logged from today onward. Try \"I'm free 3 hours tomorrow\"."

    lines = [f"- {r['date']}: {r['available_hours']}h" for r in records]
    total = round(sum(r["available_hours"] for r in records), 2)
    return "\n".join(lines + ["", f"That is {total}h in total from today onward."])


def _list_deadlines(turn: _Turn, message: str) -> str:
    deadlines = turn.call(dt.get_deadlines, status="pending")["deadlines"]
    if not deadlines:
        return "You have no pending deadlines."

    lines = ["Your pending deadlines:", ""]
    for d in deadlines:
        lines.append(f"- #{d['deadline_id']} **{d['task_name']}**: due {d['due_date']}, "
                     f"{d['estimated_hours']}h estimated, {d['priority']} priority, {d['category']}")
    return "\n".join(lines)


def _help(turn: _Turn, message: str) -> str:
    return HELP_TEXT


# ---------------------------------------------------------------------
# Intent detection: the first rule that matches wins, so order matters
# ---------------------------------------------------------------------
_ADD_VERB = r"\b(add|create)\b|\bnew\s+(deadline|task|assignment|exam|project|presentation)\b"
_QUESTION_START = r"^\s*(what|which|when|how|show|list|am|will|can|do|does|is|are)\b"
_TASK_NOUN = r"\b(assignment|homework|exam|test|quiz|project|presentation|report|essay|lab|deadline)\b"


def detect_intent(message: str):
    """Returns the function that should handle this message."""
    lower = message.lower()
    has_hours = parse_hours(message) is not None
    has_date = parse_date(message)[0] is not None
    is_question = bool(re.search(_QUESTION_START, lower)) or lower.rstrip().endswith("?")

    if re.search(r"\b(finished|completed|done with|submitted|handed in|missed|failed to)\b", lower):
        return _record_outcome

    if has_hours and re.search(r"\b(free|available|availability|spare)\b", lower) and not re.search(r"\bdue\b", lower):
        # "Do I have 3 hours free tomorrow?" asks; "Can you log 3 free hours tomorrow?" tells
        if is_question and not re.search(r"\b(log|set|add|mark|put|record|note|save)\b", lower):
            return _list_availability
        return _set_availability

    if re.search(_ADD_VERB, lower):
        return _add_deadline
    if not is_question and has_date and (
        re.search(r"\bdue\b", lower)
        or (re.search(r"\bi(?:'ve| have)\b", lower) and re.search(_TASK_NOUN, lower))
    ):
        return _add_deadline

    if re.search(r"\b(negotiat\w*|options?|extension|ways? out|trade-?offs?|what can i do)\b"
                 r"|\b(can'?t|cannot|won'?t) (make|finish)\b", lower):
        return _negotiate

    if re.search(r"\b(plan|schedule|timetable|day[- ]by[- ]day|each day)\b"
                 r"|\bwhat (should|do|can) i (do|work on) (today|tomorrow)\b", lower):
        return _plan

    if re.search(r"\b(focus|priorit\w*|make it|at risk|on track|feasib\w*|risk|status|behind|urgent)\b"
                 r"|\bhow am i doing\b|\bwhat should i (do|work on)\b", lower):
        return _focus

    if re.search(r"\b(pace|memory|learned|learnt|reliab\w*|history|weak spots?|track record|about me)\b", lower):
        return _memory

    if re.search(r"\b(availability|free (hours|time)|how many hours|when am i free)\b", lower):
        return _list_availability

    if re.search(r"\b(deadlines?|tasks?|assignments?|pending|due)\b", lower):
        return _list_deadlines

    return _help


def run_rule_agent(user_message: str, conversation_history: list = None, verbose: bool = True) -> dict:
    """
    Answers one message using rules instead of a language model.

    Same arguments and return shape as agent.run_agent, so the two can be
    swapped: final_response, conversation_history, tool_calls.
    """
    history = conversation_history[:] if conversation_history else []
    turn = _Turn(verbose)

    handler = detect_intent(user_message) if user_message.strip() else _help
    final_response = handler(turn, user_message)

    history.append({"role": "user", "text": user_message})
    history.append({"role": "agent", "text": final_response})
    return {
        "final_response": final_response,
        "conversation_history": history,
        "tool_calls": turn.tool_calls,
    }


# ---------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import storage
    sys.stdout.reconfigure(encoding="utf-8")  # the replies use emoji, also when output is redirected
    storage.init_db()
    storage.reset_db()

    for message in [
        "Add Club Poster due tomorrow, 2 hours, low priority",
        "Add DBMS assignment due in 3 days, 5 hours, high priority",
        "I'm free 2 hours today",
        "I'm free 2 hours tomorrow",
        "I have 1 hour free in 3 days",
        "Show my deadlines",
        "What should I focus on?",
        "Give me a plan",
        "I finished the Club Poster, it took 4 hours",
        "What have you learned about me?",
        "Tell me a joke",
    ]:
        print(f"\nYou: {message}")
        result = run_rule_agent(message)
        print(f"\nAgent: {result['final_response']}")
