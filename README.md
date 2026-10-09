# Personal Deadline Negotiator Agent

An AI agent that helps a student manage competing deadlines. It compares the work due with the free time actually available, learns how long tasks really take, and, when something won't fit, lays out the ways out: defer another task, ask for an extension, find more time, or reduce scope.

An agent decides which tools to call for each message, so the system is not a fixed script. With a Gemini API key the agent is a language model (Google Gemini). Without one, a built-in rule-based agent does the same job, so the whole project runs with no key and no cost.

## Modules

| # | Module | File | What it does |
|---|--------|------|--------------|
| 1 | Data storage | `storage.py` | SQLite database with four tables: deadlines, availability, memory, history |
| 2 | Deadline tool | `deadline_tool.py` | Add, list and update deadlines, with validation |
| 3 | Availability tool | `availability_tool.py` | Log and query free hours per day |
| 4 | Reprioritization tool | `reprioritization_tool.py` | Flags each pending deadline as safe, tight or at risk |
| 5 | Memory | `memory.py` | Learns a pace multiplier and which categories of deadline tend to be missed |
| 6 | Agent orchestration | `agent.py` | Gemini tool-calling loop over all the tools; hands over to the rule-based agent when no key is set |
| 6b | Rule-based agent | `rule_agent.py` | Keyword and pattern rules that pick the tools, parse dates and hours, and choose which option to recommend |
| 7 | Negotiation tool | `negotiation_tool.py` | Day-by-day plan and negotiation options for deadlines that don't fit |

`app.py` is a Streamlit interface over all seven modules. `demo.py` is a narrated terminal walkthrough of Modules 1 to 5 and 7.

## Setup

Requires Python 3.10 or newer.

```
pip install -r requirements.txt
```

No key is needed: everything runs on the rule-based agent out of the box.

To use the Gemini language model instead, which understands free-form questions, get a free key from [Google AI Studio](https://aistudio.google.com) and put it in the `GEMINI_API_KEY` environment variable. On Windows PowerShell:

```
[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "your-key-here", "User")
```

Restart the terminal afterwards. The chat tab shows which mode is active.

In Gemini mode the agent uses the `gemini-3.8-flash` model. To use a different one, set the `GEMINI_MODEL` environment variable.

## Running

| Command | What you get |
|---------|--------------|
| `streamlit run app.py` | The web interface, including the chat tab |
| `python agent.py` | The agent as a terminal chat, with seeded example data |
| `python demo.py` | The walkthrough of Modules 1 to 5 and 7, with no API key needed |
| `python <module>.py` | That module's self-test, for example `python negotiation_tool.py` |

`agent.py`, `demo.py` and the module self-tests clear the database before they run.

## How the pieces fit

1. Deadlines and free hours are entered through the tools (Modules 2 and 3) and stored by Module 1.
2. Module 4 multiplies each estimate by the learned pace and gives free hours to the earliest deadline first. A deadline that cannot be covered is at risk.
3. Module 7 turns the same allocation into a daily plan and, for each at-risk deadline, a list of options.
4. When a deadline is closed out, Module 5 updates the pace multiplier and the per-category miss rates.
5. Module 6 gives the agent all of these as tools. The agent chooses which to call, recommends one option, and logs the recommendation. In Gemini mode the model makes those choices; in rule mode `rule_agent.py` makes them with fixed rules.

## What the rule-based agent understands

| You type | It does |
|----------|---------|
| "Add DBMS assignment due Friday, 5 hours, high priority" | Adds the deadline |
| "I'm free 3 hours tomorrow" | Logs free hours |
| "What should I focus on?" | Checks feasibility and recommends one option for anything at risk |
| "Give me a plan" | Builds the day-by-day plan |
| "What are my options?" | Lists every option for each deadline that doesn't fit |
| "I finished the DBMS assignment, it took 6 hours" | Records the outcome and updates the pace |
| "Show my deadlines", "Show my free hours", "What have you learned about me?" | Looks things up |

Anything else gets a reply listing these. Dates can be written as `2026-10-15`, "today", "tomorrow", "in 3 days", "15 Oct" or a weekday name.
