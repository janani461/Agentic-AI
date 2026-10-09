"""
Module 6: Agent Orchestration
---------------------------------
This is the actual "agent brain." Unlike Modules 1-5 (which are just
deterministic functions), this module lets an LLM (Google Gemini) decide:
    - which tool(s) to call
    - in what order
    - whether to call a tool at all, or just answer from context/memory

This is what makes the system an AGENT instead of a script. The LLM is
given the tool schemas + a system prompt describing its role, and for
every user message, it reasons about what it needs before answering.

Flow:
    1. User sends a message (e.g. "what should I focus on today?")
    2. Gemini decides: does it need to call a tool? Which one(s)?
    3. If yes -> we execute the real Python function -> feed result back to Gemini
    4. Gemini may decide it needs ANOTHER tool call based on that result
    5. Once Gemini has enough info, it gives a final natural-language answer

Requires: pip install google-genai
Requires: a free API key from https://aistudio.google.com set as the
          environment variable GEMINI_API_KEY

No key? run_agent() then hands the message to the rule-based agent in
rule_agent.py, which makes the same decisions with plain Python rules.
The project runs in full either way.
"""

import os
from datetime import date
from google import genai
from google.genai import types

import deadline_tool as dt
import availability_tool as at
import reprioritization_tool as rt
import memory as mem
import negotiation_tool as nt
import rule_agent

# ---------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")  # free-tier model with tool use

_client = None


def has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def agent_mode() -> str:
    """'gemini' when an API key is set, otherwise 'rules'."""
    return "gemini" if has_api_key() else "rules"


def get_client():
    """Creates the Gemini client on first use, so importing this module never needs a key."""
    global _client
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY from the environment
    return _client

# ---------------------------------------------------------------------
# Register all tools (schemas from Modules 2, 3, 4, 5, 7)
# ---------------------------------------------------------------------
ALL_TOOL_SCHEMAS = [
    dt.ADD_DEADLINE_SCHEMA,
    dt.GET_DEADLINES_SCHEMA,
    dt.UPDATE_DEADLINE_STATUS_SCHEMA,
    at.SET_AVAILABILITY_SCHEMA,
    at.GET_AVAILABILITY_SCHEMA,
    rt.TOOL_SCHEMA,
    mem.RECORD_OUTCOME_SCHEMA,
    mem.GET_MEMORY_SCHEMA,
    nt.BUILD_PLAN_SCHEMA,
    nt.GET_NEGOTIATION_OPTIONS_SCHEMA,
    nt.LOG_RECOMMENDATION_SCHEMA,
]

# Map tool name -> actual Python function to call
TOOL_FUNCTIONS = {
    "add_deadline": dt.add_deadline,
    "get_deadlines": dt.get_deadlines,
    "update_deadline_status": dt.update_deadline_status,
    "set_availability": at.set_availability,
    "get_availability": at.get_availability,
    "check_feasibility": rt.check_feasibility,
    "record_outcome": mem.record_outcome,
    "get_all_memory": mem.get_all_memory,
    "build_plan": nt.build_plan,
    "get_negotiation_options": nt.get_negotiation_options,
    "log_recommendation": nt.log_recommendation,
}

# The modules describe each tool as {name, description, input_schema};
# Gemini takes the same three things as a FunctionDeclaration
GEMINI_TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=schema["name"],
        description=schema["description"],
        parameters_json_schema=schema["input_schema"],
    )
    for schema in ALL_TOOL_SCHEMAS
])]

SYSTEM_PROMPT = """You are a Personal Deadline Negotiator Agent. Your job is to help
the user manage competing deadlines given their real available time and their
personal work pace (which you learn over time from their history).

You have access to tools for: adding/querying deadlines, logging/querying
availability, checking feasibility of deadlines against available time,
building a day-by-day plan, listing negotiation options for deadlines that
don't fit, and recording outcomes to improve future predictions.

Behave like a thoughtful advisor, not a calculator:
- Decide for yourself which tool(s) you need to call based on what the user is asking.
  Don't call a tool just because it exists — only call what's actually needed.
- If the user asks a prioritization question ("what should I focus on?", "am I going
  to make it?"), you likely need BOTH current deadlines/availability context AND the
  feasibility check — call check_feasibility, which already combines everything.
- If a deadline is at risk, don't stop at the warning: call get_negotiation_options,
  recommend ONE option and say why it beats the others (priority, how big the
  shortfall is, how realistic an extension is), then save it with log_recommendation.
- If the user asks for a schedule or what to do each day, call build_plan.
- When adding a deadline, pick the category that fits the task (exam, presentation,
  project, assignment) so memory can learn which kinds the user tends to miss. If
  memory shows a weak-spot category, treat pending deadlines of that kind as riskier.
- If the user is just logging data (adding a deadline, logging free hours), only
  call the relevant single tool — don't over-call.
- When giving a final answer, don't just dump raw tool output. Explain your reasoning:
  mention the user's pace multiplier or reliability history when it's relevant to
  why you're recommending something.
- Be concise and direct. This is a student under time pressure, not looking for essays.
"""


def build_system_prompt() -> str:
    """Adds today's date so the agent can turn "Friday" or "tomorrow" into YYYY-MM-DD."""
    today = date.today()
    return f"{SYSTEM_PROMPT}\nToday's date is {today.isoformat()} ({today.strftime('%A')})."


def call_tool(tool_name: str, tool_input: dict) -> dict:
    """Executes the real Python function behind a tool name, with the LLM's chosen arguments."""
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}
    try:
        return func(**tool_input)
    except Exception as e:
        return {"status": "error", "message": f"Tool execution failed: {str(e)}"}


def run_agent(user_message: str, conversation_history: list = None, verbose: bool = True) -> dict:
    """
    Answers one user message with whichever agent is available: Gemini
    when an API key is set, the rule-based agent otherwise.

    Args:
        user_message: what the user typed
        conversation_history: list of prior turns (optional, for multi-turn chat)
        verbose: if True, prints each tool call as it happens (useful for demo)

    Returns:
        dict with the final text response, the full updated conversation
        history, the list of tool calls made while answering, and the
        mode that answered ('gemini' or 'rules')
    """
    mode = agent_mode()
    run = run_gemini_agent if mode == "gemini" else rule_agent.run_rule_agent
    result = run(user_message, conversation_history=conversation_history, verbose=verbose)
    result["mode"] = mode
    return result


def run_gemini_agent(user_message: str, conversation_history: list = None, verbose: bool = True) -> dict:
    """
    Sends a user message to the agent, letting Gemini decide tool calls
    dynamically until it produces a final natural-language answer.

    Args:
        user_message: what the user typed
        conversation_history: list of prior turns (optional, for multi-turn chat)
        verbose: if True, prints each tool call as it happens (useful for demo)

    Returns:
        dict with the final text response, the full updated conversation
        history, and the list of tool calls made while answering
    """
    messages = conversation_history[:] if conversation_history else []
    messages.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=GEMINI_TOOLS,
    )
    tool_calls = []

    # Loop: keep going as long as Gemini wants to call tools
    while True:
        response = get_client().models.generate_content(
            model=MODEL,
            contents=messages,
            config=config,
        )

        # Keep Gemini's own turn in the history exactly as it came back
        if response.candidates and response.candidates[0].content:
            messages.append(response.candidates[0].content)

        # Did Gemini decide to call any tools this turn?
        function_calls = response.function_calls or []

        if not function_calls:
            # No more tools needed -> Gemini has given its final answer
            return {
                "final_response": response.text or "(The model returned no answer.)",
                "conversation_history": messages,
                "tool_calls": tool_calls,
            }

        # Gemini wants to call one or more tools -> execute them for real
        tool_results = []
        for call in function_calls:
            tool_input = dict(call.args or {})
            if verbose:
                print(f"   🔧 Agent is calling: {call.name}({tool_input})")

            result = call_tool(call.name, tool_input)

            if verbose:
                print(f"      -> {result}")

            tool_calls.append({"name": call.name, "input": tool_input})
            tool_results.append(types.Part(function_response=types.FunctionResponse(
                id=call.id,
                name=call.name,
                response=result,
            )))

        # Feed tool results back to Gemini so it can decide the next step
        messages.append(types.Content(role="user", parts=tool_results))
        # loop continues -> Gemini either calls more tools or gives final answer


# ---------------------------------------------------------------------
# Quick interactive test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta
    import storage
    storage.init_db()
    storage.reset_db()

    # dates are relative to today so the seed data never goes stale
    def days_from_now(n):
        return (date.today() + timedelta(days=n)).isoformat()

    # Seed some realistic data so the agent has something to reason about
    dt.add_deadline("DBMS Assignment", days_from_now(3), estimated_hours=5, priority="high")
    dt.add_deadline("Presentation Prep", days_from_now(2), estimated_hours=3, priority="medium")
    at.set_availability(days_from_now(0), 2)
    at.set_availability(days_from_now(1), 2)
    at.set_availability(days_from_now(2), 1)
    at.set_availability(days_from_now(3), 2)
    storage.set_memory("pace_multiplier", "1.5")

    print("=" * 60)
    print(f"Mode: {agent_mode()}" + ("" if has_api_key() else " (no GEMINI_API_KEY set, using built-in rules)"))
    print("AGENT DEMO — type 'quit' to exit")
    print("=" * 60)

    history = []
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ("quit", "exit"):
            break

        result = run_agent(user_input, conversation_history=history)
        history = result["conversation_history"]
        print(f"\nAgent: {result['final_response']}")