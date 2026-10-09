# Personal Deadline Negotiator Agent

An AI agent that helps a student manage competing deadlines. It compares the work due with the free time actually available, learns how long tasks really take, and, when something won't fit, lays out the ways out: defer another task, ask for an extension, find more time, or reduce scope.

Claude decides which tools to call for each message, so the system is an agent and not a fixed script.

## Modules

| # | Module | File | What it does |
|---|--------|------|--------------|
| 1 | Data storage | `storage.py` | SQLite database with four tables: deadlines, availability, memory, history |
| 2 | Deadline tool | `deadline_tool.py` | Add, list and update deadlines, with validation |
| 3 | Availability tool | `availability_tool.py` | Log and query free hours per day |
| 4 | Reprioritization tool | `reprioritization_tool.py` | Flags each pending deadline as safe, tight or at risk |
| 5 | Memory | `memory.py` | Learns a pace multiplier and which categories of deadline tend to be missed |
| 6 | Agent orchestration | `agent.py` | Claude tool-use loop over all the tools |
| 7 | Negotiation tool | `negotiation_tool.py` | Day-by-day plan and negotiation options for deadlines that don't fit |

`app.py` is a Streamlit interface over all seven modules. `demo.py` is a narrated terminal walkthrough of Modules 1 to 5.

## Setup

Requires Python 3.10 or newer.

```
pip install -r requirements.txt
```

The agent (Module 6 and the chat tab) needs an Anthropic API key in the `ANTHROPIC_API_KEY` environment variable. On Windows PowerShell:

```
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-your-key-here", "User")
```

Restart the terminal afterwards. Modules 1 to 5 and 7 run without a key.

## Running

| Command | What you get |
|---------|--------------|
| `streamlit run app.py` | The web interface, including the chat tab |
| `python agent.py` | The agent as a terminal chat, with seeded example data |
| `python demo.py` | The walkthrough of Modules 1 to 5 |
| `python <module>.py` | That module's self-test, for example `python negotiation_tool.py` |

`agent.py`, `demo.py` and the module self-tests clear the database before they run.

## How the pieces fit

1. Deadlines and free hours are entered through the tools (Modules 2 and 3) and stored by Module 1.
2. Module 4 multiplies each estimate by the learned pace and gives free hours to the earliest deadline first. A deadline that cannot be covered is at risk.
3. Module 7 turns the same allocation into a daily plan and, for each at-risk deadline, a list of options.
4. When a deadline is closed out, Module 5 updates the pace multiplier and the per-category miss rates.
5. Module 6 gives Claude all of these as tools. Claude chooses which to call, recommends one option, and logs the recommendation.
