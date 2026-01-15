import pandas as pd
import streamlit as st

st.title("🔍 Data Lake Audit")

file = st.file_uploader("Upload audit file", type=['jsonl','csv','xlsx'], key="audit_file")

if file:
    if file.name.endswith('.jsonl'): df = pd.read_json(file, lines=True)
    elif file.name.endswith('.csv'): df = pd.read_csv(file)
    else: df = pd.read_excel(file)
    st.dataframe(df.head(50), use_container_width=True)
else:
    try: st.dataframe(pd.read_json('validation_audit.jsonl', lines=True).tail(50), use_container_width=True)
    except: st.info("No audit log found.")