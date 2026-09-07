"""
Module 6: Agent Orchestration
---------------------------------
This is the actual "agent brain." Unlike Modules 1-5 (which are just
deterministic functions), this module lets an LLM (Claude) decide:
    - which tool(s) to call
    - in what order
    - whether to call a tool at all, or just answer from context/memory

This is what makes the system an AGENT instead of a script. The LLM is
given the 3 tool schemas + a system prompt describing its role, and for
every user message, it reasons about what it needs before answering.

Flow:
    1. User sends a message (e.g. "what should I focus on today?")
    2. Claude decides: does it need to call a tool? Which one(s)?
    3. If yes -> we execute the real Python function -> feed result back to Claude
    4. Claude may decide it needs ANOTHER tool call based on that result
    5. Once Claude has enough info, it gives a final natural-language answer

Requires: pip install anthropic
Requires: an API key set as an environment variable ANTHROPIC_API_KEY
"""

import os
import json
import anthropic

import deadline_tool as dt
import availability_tool as at
import reprioritization_tool as rt
import memory as mem

# ---------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-5-20250929"  # any current Claude model with tool use works

# ---------------------------------------------------------------------
# Register all tools (schemas from Modules 2, 3, 4, 5)
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
}

SYSTEM_PROMPT = """You are a Personal Deadline Negotiator Agent. Your job is to help
the user manage competing deadlines given their real available time and their
personal work pace (which you learn over time from their history).

You have access to tools for: adding/querying deadlines, logging/querying
availability, checking feasibility of deadlines against available time, and
recording outcomes to improve future predictions.

Behave like a thoughtful advisor, not a calculator:
- Decide for yourself which tool(s) you need to call based on what the user is asking.
  Don't call a tool just because it exists — only call what's actually needed.
- If the user asks a prioritization question ("what should I focus on?", "am I going
  to make it?"), you likely need BOTH current deadlines/availability context AND the
  feasibility check — call check_feasibility, which already combines everything.
- If the user is just logging data (adding a deadline, logging free hours), only
  call the relevant single tool — don't over-call.
- When giving a final answer, don't just dump raw tool output. Explain your reasoning:
  mention the user's pace multiplier or reliability history when it's relevant to
  why you're recommending something.
- Be concise and direct. This is a student under time pressure, not looking for essays.
"""


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
    Sends a user message to the agent, letting Claude decide tool calls
    dynamically until it produces a final natural-language answer.

    Args:
        user_message: what the user typed
        conversation_history: list of prior turns (optional, for multi-turn chat)
        verbose: if True, prints each tool call as it happens (useful for demo)

    Returns:
        dict with the final text response and the full updated conversation history
    """
    messages = conversation_history[:] if conversation_history else []
    messages.append({"role": "user", "content": user_message})

    # Loop: keep going as long as Claude wants to call tools
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOL_SCHEMAS,
            messages=messages,
        )

        # Did Claude decide to call any tools this turn?
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            # No more tools needed -> Claude has given its final answer
            final_text = "".join(b.text for b in response.content if b.type == "text")
            messages.append({"role": "assistant", "content": response.content})
            return {"final_response": final_text, "conversation_history": messages}

        # Claude wants to call one or more tools -> execute them for real
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            if verbose:
                print(f"   🔧 Agent is calling: {block.name}({block.input})")

            result = call_tool(block.name, block.input)

            if verbose:
                print(f"      -> {result}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        # Feed tool results back to Claude so it can decide the next step
        messages.append({"role": "user", "content": tool_results})
        # loop continues -> Claude either calls more tools or gives final answer


# ---------------------------------------------------------------------
# Quick interactive test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import storage
    storage.init_db()
    storage.reset_db()

    # Seed some realistic data so the agent has something to reason about
    dt.add_deadline("DBMS Assignment", "2026-09-08", estimated_hours=5, priority="high")
    dt.add_deadline("Presentation Prep", "2026-09-07", estimated_hours=3, priority="medium")
    at.set_availability("2026-09-05", 2)
    at.set_availability("2026-09-06", 2)
    at.set_availability("2026-09-07", 1)
    at.set_availability("2026-09-08", 2)
    storage.set_memory("pace_multiplier", "1.5")

    print("=" * 60)
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