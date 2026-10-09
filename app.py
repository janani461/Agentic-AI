"""
Streamlit App — Deadline Negotiator Agent (Modules 1-7)
----------------------------------------------------------------
Run this with: streamlit run app.py

This gives a clickable UI on top of the existing modules, instead of
showing raw terminal output. It does NOT replace demo.py's logic — it
just wraps the same functions (storage, deadline_tool, availability_tool,
reprioritization_tool, memory, negotiation_tool) in a web interface, and
adds a chat tab that talks to the agent (agent.py).
"""

import os
from google.genai import errors as genai_errors
import streamlit as st
import storage
import deadline_tool as dt
import availability_tool as at
import reprioritization_tool as rt
import memory as mem
import negotiation_tool as nt
import agent

st.set_page_config(page_title="Deadline Negotiator Agent", page_icon="📅", layout="wide")

# Initialize the database once per session
storage.init_db()

st.title("📅 Deadline Negotiator Agent")
st.caption("Storage, tools, memory, negotiation and the agent working together")

# Sidebar: reset button for clean demo runs
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Reset Database", width="stretch"):
        storage.reset_db()
        st.session_state.pop("chat_log", None)
        st.session_state.pop("agent_history", None)
        st.success("Database cleared!")
        st.rerun()

    st.divider()
    pace = mem.get_pace_multiplier()
    st.metric("Learned Pace Multiplier", f"{pace}x")
    st.caption("1.0 = trusts your estimate exactly. Higher = you tend to underestimate.")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "1️⃣ Add Deadline", "2️⃣ Log Availability", "3️⃣ Check Feasibility",
    "4️⃣ Plan & Negotiate", "5️⃣ Record Outcome", "6️⃣ Chat with Agent",
])

# -----------------------------------------------------------------------
# TAB 1: Deadline Tool
# -----------------------------------------------------------------------
with tab1:
    st.subheader("Add a New Deadline")
    col1, col2 = st.columns(2)
    with col1:
        task_name = st.text_input("Task name", placeholder="e.g. DBMS Assignment")
        due_date = st.date_input("Due date")
        category = st.selectbox("Category", sorted(dt.VALID_CATEGORIES))
    with col2:
        estimated_hours = st.number_input("Estimated hours", min_value=0.5, value=3.0, step=0.5)
        priority = st.selectbox("Priority", ["low", "medium", "high"])

    if st.button("Add Deadline", type="primary"):
        result = dt.add_deadline(task_name, due_date.isoformat(), estimated_hours, priority, category)
        if result["status"] == "success":
            st.success(result["message"])
        else:
            st.error(result["message"])

    st.divider()
    st.subheader("Current Deadlines")
    deadlines_result = dt.get_deadlines()
    if deadlines_result["deadlines"]:
        st.dataframe(deadlines_result["deadlines"], width="stretch", hide_index=True)
    else:
        st.info("No deadlines added yet.")

# -----------------------------------------------------------------------
# TAB 2: Availability Tool
# -----------------------------------------------------------------------
with tab2:
    st.subheader("Log Your Free Hours")
    col1, col2 = st.columns(2)
    with col1:
        avail_date = st.date_input("Date", key="avail_date")
    with col2:
        avail_hours = st.number_input("Available hours", min_value=0.0, max_value=24.0, value=2.0, step=0.5)

    if st.button("Save Availability", type="primary"):
        result = at.set_availability(avail_date.isoformat(), avail_hours)
        if result["status"] == "success":
            st.success(result["message"])
        else:
            st.error(result["message"])

    st.divider()
    st.subheader("Logged Availability")
    avail_result = at.get_availability()
    if avail_result["availability"]:
        st.dataframe(avail_result["availability"], width="stretch", hide_index=True)
        st.metric("Total hours logged", avail_result["total_available_hours"])
    else:
        st.info("No availability logged yet.")

# -----------------------------------------------------------------------
# TAB 3: Reprioritization Tool (the "wow" moment)
# -----------------------------------------------------------------------
with tab3:
    st.subheader("Feasibility Check")
    st.caption("Combines your deadlines + availability + learned pace to flag what's at risk.")

    if st.button("🔍 Run Feasibility Check", type="primary"):
        result = rt.check_feasibility()

        if result["status"] != "success" or not result.get("results"):
            st.warning(result.get("message", "No pending deadlines to check."))
        else:
            st.write(f"**Pace multiplier used:** {result['pace_multiplier_used']}x")

            for item in result["results"]:
                risk = item["risk_level"]
                color = {"at_risk": "🔴", "tight": "🟡", "safe": "🟢"}[risk]

                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        st.markdown(f"### {color} {item['task_name']}")
                        st.caption(f"Due: {item['due_date']} · Priority: {item['priority']}")
                    with c2:
                        st.metric("Hours needed", item["hours_needed_with_pace"])
                    with c3:
                        st.metric("Hours available", item["hours_available_before_due"])

                    if risk == "at_risk":
                        st.error(f"⚠️ At risk of being missed — not enough time even accounting for your pace.")
                    elif risk == "tight":
                        st.warning("Cutting it close — little buffer left.")
                    else:
                        st.success("On track.")

            if result["at_risk_tasks"]:
                st.divider()
                st.markdown(f"### 🎯 Focus recommendation")
                st.markdown(f"Prioritize: **{', '.join(result['at_risk_tasks'])}**")

# -----------------------------------------------------------------------
# TAB 4: Negotiation Tool
# -----------------------------------------------------------------------
with tab4:
    st.subheader("Day-by-Day Plan")
    st.caption("Your free hours assigned to pending deadlines, earliest due date first.")

    plan = nt.build_plan()
    if not plan.get("schedule"):
        st.info("Nothing to plan yet. Add a pending deadline and some availability first.")
    else:
        rows = [
            {"date": day["date"], "task": work["task_name"], "hours": work["hours"]}
            for day in plan["schedule"] for work in day["work"]
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(f"Free hours left unused: {plan['unscheduled_free_hours']}")

    st.divider()
    st.subheader("Negotiation Options")
    st.caption("For each deadline that doesn't fit, the ways out.")

    negotiation = nt.get_negotiation_options()
    if not negotiation["negotiations"]:
        st.success(negotiation.get("message", "Nothing to negotiate."))
    else:
        for item in negotiation["negotiations"]:
            with st.container(border=True):
                st.markdown(f"### 🔴 {item['task_name']}")
                st.caption(f"Due: {item['due_date']} · Priority: {item['priority']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Hours needed", item["hours_needed"])
                c2.metric("Hours scheduled", item["hours_scheduled"])
                c3.metric("Short by", item["shortfall"])

                for option in item["options"]:
                    label = option["type"].replace("_", " ").capitalize()
                    st.markdown(f"- **{label}:** {option['description']}")

# -----------------------------------------------------------------------
# TAB 5: Memory Module
# -----------------------------------------------------------------------
with tab5:
    st.subheader("Record a Completed/Missed Deadline")
    st.caption("This teaches the agent your real work pace.")

    deadlines_list = dt.get_deadlines()["deadlines"]
    if not deadlines_list:
        st.info("Add a deadline first in Tab 1.")
    else:
        options = {f"#{d['deadline_id']} - {d['task_name']}": d["deadline_id"] for d in deadlines_list}
        selected_label = st.selectbox("Select deadline", list(options.keys()))
        selected_id = options[selected_label]

        col1, col2 = st.columns(2)
        with col1:
            actual_hours = st.number_input("Actual hours it took", min_value=0.5, value=3.0, step=0.5)
        with col2:
            outcome = st.selectbox("Outcome", ["met", "missed"])

        if st.button("Record Outcome", type="primary"):
            result = mem.record_outcome(selected_id, actual_hours, outcome)
            if result["status"] == "success":
                st.success(result["message"])
                st.info(f"Updated pace multiplier: **{result['updated_pace_multiplier']}x**")
            else:
                st.error(result["message"])

    st.divider()
    st.subheader("Reliability Summary")
    summary = mem.get_reliability_summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("Deadlines tracked", summary["total_tracked"])
    c2.metric("Met", summary["met_count"])
    c3.metric("Missed", summary["missed_count"])
    if summary["missed_rate"] is not None:
        st.progress(summary["missed_rate"], text=f"Miss rate: {summary['missed_rate']*100:.0f}%")

    patterns = mem.get_category_patterns()
    if patterns["categories"]:
        st.subheader("By Category")
        st.dataframe(patterns["categories"], width="stretch", hide_index=True)
        if patterns["weak_spots"]:
            st.warning(f"You tend to miss: **{', '.join(patterns['weak_spots'])}** deadlines.")

# -----------------------------------------------------------------------
# TAB 6: Agent Orchestration (chat)
# -----------------------------------------------------------------------
with tab6:
    st.subheader("Chat with the Agent")
    st.caption("Ask in plain language. The agent decides which tools to call.")

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        st.warning("Set the GEMINI_API_KEY environment variable and restart the app to use the chat.")
    else:
        chat_log = st.session_state.setdefault("chat_log", [])              # what is shown on screen
        agent_history = st.session_state.setdefault("agent_history", [])    # what is sent back to Gemini

        for entry in chat_log:
            with st.chat_message(entry["role"]):
                if entry.get("tool_calls"):
                    with st.expander(f"🔧 Tools called: {len(entry['tool_calls'])}"):
                        for call in entry["tool_calls"]:
                            st.code(f"{call['name']}({call['input']})")
                st.markdown(entry["text"])

        prompt = st.chat_input("e.g. What should I focus on today?")
        if prompt:
            try:
                with st.spinner("Thinking..."):
                    result = agent.run_agent(prompt, conversation_history=agent_history, verbose=False)
            except genai_errors.APIError as e:
                if e.code == 429:
                    st.error("The free tier's rate limit was hit. Wait a minute and try again.")
                elif e.code in (400, 401, 403):
                    st.error(f"Gemini rejected the request. Check GEMINI_API_KEY and restart the app. ({e.message})")
                else:
                    st.error(f"The agent could not answer: {e}")
            else:
                chat_log.append({"role": "user", "text": prompt})
                chat_log.append({"role": "assistant", "text": result["final_response"],
                                 "tool_calls": result["tool_calls"]})
                st.session_state["agent_history"] = result["conversation_history"]
                st.rerun()
