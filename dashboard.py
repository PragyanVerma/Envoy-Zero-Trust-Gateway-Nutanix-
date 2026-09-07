import streamlit as st
import pandas as pd
import json
import os
import time

st.set_page_config(page_title="Envoy ML Rate Limit Dashboard", layout="wide")

st.title("Live ML Rate Limit Dashboard")

LOG_FILE = "logs/requests.log"

def load_data():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame()
        
    data = []
    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not data:
        return pd.DataFrame()
        
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

df = load_data()

if df.empty:
    st.warning("No data in logs/requests.log yet. Send some traffic!")
else:
    total_reqs = len(df)
    sandboxed = len(df[df['route'] == 'sandbox'])
    standard = len(df[df['route'] == 'standard'])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Requests", total_reqs)
    c2.metric("Routed to Standard", standard)
    c3.metric("Routed to Sandbox", sandboxed)
    
    st.subheader("Trust Score over Time (by caller)")
    chart_data = df.pivot(index='timestamp', columns='caller_id', values='trust_score')
    chart_data = chart_data.fillna(method='ffill').fillna(method='bfill')
    st.line_chart(chart_data)
    
    st.subheader("Recent Requests Table")
    st.dataframe(df.sort_values(by='timestamp', ascending=False).head(20))

time.sleep(2)
st.rerun()
