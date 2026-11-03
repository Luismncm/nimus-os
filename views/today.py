import streamlit as st
from views.workbench import workbench

# One page of work: the summary and its fronts (produce, deliver, supply, collect, pay) hold every tool of the day.
workbench(st.session_state['snapshot'])
