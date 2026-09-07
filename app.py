"""
Streamlit App — Deadline Negotiator Agent (Modules 1-5 Demo)
----------------------------------------------------------------
Run this with: streamlit run app.py

This gives a clickable UI on top of the existing modules, instead of
showing raw terminal output. It does NOT replace demo.py's logic — it
just wraps the same functions (storage, deadline_tool, availability_tool,
reprioritization_tool, memory) in a web interface.
"""

import streamlit as st
import storage
import deadline_tool as dt
import availability_tool as at
import reprioritization_tool as rt
import memory as mem

st.set_page_config(page_title="Deadline Negotiator Agent", page_icon="📅", layout="wide")

# Initialize the database once per session
storage.init_db()

st.title("📅 Deadline Negotiator Agent")
st.caption("Modules 1-5 demo — Storage, 3 Tools, and Memory working together")

# Sidebar: reset button for clean demo runs
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Reset Database", use_container_width=True):
        storage.reset_db()
        st.success("Database cleared!")
        st.rerun()

    st.divider()
    pace = mem.get_pace_multiplier()
    st.metric("Learned Pace Multiplier", f"{pace}x")
    st.caption("1.0 = trusts your estimate exactly. Higher = you tend to underestimate.")

tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Add Deadline", "2️⃣ Log Availability", "3️⃣ Check Feasibility", "4️⃣ Record Outcome"
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
    with col2:
        estimated_hours = st.number_input("Estimated hours", min_value=0.5, value=3.0, step=0.5)
        priority = st.selectbox("Priority", ["low", "medium", "high"])

    if st.button("Add Deadline", type="primary"):
        result = dt.add_deadline(task_name, due_date.isoformat(), estimated_hours, priority)
        if result["status"] == "success":
            st.success(result["message"])
        else:
            st.error(result["message"])

    st.divider()
    st.subheader("Current Deadlines")
    deadlines_result = dt.get_deadlines()
    if deadlines_result["deadlines"]:
        st.dataframe(deadlines_result["deadlines"], use_container_width=True, hide_index=True)
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
        st.dataframe(avail_result["availability"], use_container_width=True, hide_index=True)
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
# TAB 4: Memory Module
# -----------------------------------------------------------------------
with tab4:
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