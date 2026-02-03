import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import altair as alt

# Import shared utilities
from streamlit_app import standardize_input_data

st.title("📈 Weekly Analysis Dashboard")

st.info("Upload multiple 'Full Data' files exported from the Daily tab to see aggregated trends.")

weekly_files = st.file_uploader("Upload Full Data Files (XLSX/CSV)", accept_multiple_files=True, type=['xlsx', 'csv'], key="weekly_files", label_visibility="collapsed")

if weekly_files:
    combined_df = pd.DataFrame()
    with st.spinner("Aggregating files..."):
        for f in weekly_files:
            try:
                if f.name.endswith('.xlsx'):
                    try: df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                    except: f.seek(0); df = pd.read_excel(f, engine='openpyxl', dtype=str)
                else: df = pd.read_csv(f, dtype=str)
                df.columns = df.columns.str.strip()
                df = standardize_input_data(df)
                for col in ['Status', 'Reason', 'FLAG', 'SELLER_NAME', 'CATEGORY', 'PRODUCT_SET_SID']:
                    if col not in df.columns: df[col] = pd.NA
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e: st.error(f"Error reading {f.name}: {e}")

    if not combined_df.empty:
        combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
        rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()
        st.markdown("### Key Metrics")
        with st.container():
            m1, m2, m3, m4 = st.columns(4)
            total = len(combined_df); rej_count = len(rejected); rej_rate = (rej_count/total * 100) if total else 0
            m1.metric("Total Products Checked", f"{total:,}"); m2.metric("Total Rejected", f"{rej_count:,}"); m3.metric("Rejection Rate", f"{rej_rate:.1f}%"); m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top Rejection Reasons (Flags)")
            if not rejected.empty and 'FLAG' in rejected.columns:
                reason_counts = rejected['FLAG'].value_counts().reset_index(); reason_counts.columns = ['Flag', 'Count']
                chart = alt.Chart(reason_counts.head(10)).mark_bar().encode(x=alt.X('Count'), y=alt.Y('Flag', sort='-x'), color=alt.value('#FF6B6B'), tooltip=['Flag', 'Count']).interactive()
                st.altair_chart(chart, use_container_width=True)
        with c2:
            st.subheader("Top Rejected Categories")
            if not rejected.empty and 'CATEGORY' in rejected.columns:
                cat_counts = rejected['CATEGORY'].value_counts().reset_index(); cat_counts.columns = ['Category', 'Count']
                chart = alt.Chart(cat_counts.head(10)).mark_bar().encode(x=alt.X('Count'), y=alt.Y('Category', sort='-x'), color=alt.value('#4ECDC4'), tooltip=['Category', 'Count']).interactive()
                st.altair_chart(chart, use_container_width=True)
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Seller Trust Score (Top 10)")
            if not combined_df.empty and 'SELLER_NAME' in combined_df.columns:
                seller_stats = combined_df.groupby('SELLER_NAME').agg(Total=('PRODUCT_SET_SID', 'count'), Rejected=('Status', lambda x: (x == 'Rejected').sum()))
                seller_stats['Trust Score'] = 100 - (seller_stats['Rejected'] / seller_stats['Total'] * 100)
                seller_stats = seller_stats.sort_values('Rejected', ascending=False).head(10).reset_index()
                chart = alt.Chart(seller_stats).mark_bar().encode(x=alt.X('SELLER_NAME', sort='-y'), y=alt.Y('Trust Score', scale=alt.Scale(domain=[0, 100])), color=alt.Color('Trust Score', scale=alt.Scale(scheme='redyellowgreen')), tooltip=['SELLER_NAME', 'Total', 'Rejected', 'Trust Score']).interactive()
                st.altair_chart(chart, use_container_width=True)
        with c4:
            st.subheader("Seller vs. Reason Breakdown (Top 5)")
            if not rejected.empty and 'SELLER_NAME' in rejected.columns and 'Reason' in rejected.columns:
                top_sellers = rejected['SELLER_NAME'].value_counts().head(5).index.tolist()
                filtered_rej = rejected[rejected['SELLER_NAME'].isin(top_sellers)]
                if not filtered_rej.empty:
                    breakdown = filtered_rej.groupby(['SELLER_NAME', 'Reason']).size().reset_index(name='Count')
                    chart = alt.Chart(breakdown).mark_bar().encode(x=alt.X('SELLER_NAME'), y=alt.Y('Count'), color=alt.Color('Reason'), tooltip=['SELLER_NAME', 'Reason', 'Count']).interactive()
                    st.altair_chart(chart, use_container_width=True)
        st.markdown("---")
        st.subheader("Top 5 Summaries")
        if not rejected.empty:
            top_reasons = rejected['FLAG'].value_counts().head(5).reset_index(); top_reasons.columns = ['Flag', 'Count']
            top_sellers = rejected['SELLER_NAME'].value_counts().head(5).reset_index(); top_sellers.columns = ['Seller', 'Rejection Count']
            top_cats = rejected['CATEGORY'].value_counts().head(5).reset_index(); top_cats.columns = ['Category', 'Rejection Count']
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown("**Top 5 Reasons**"); st.dataframe(top_reasons, hide_index=True, use_container_width=True)
            with c2: st.markdown("**Top 5 Sellers**"); st.dataframe(top_sellers, hide_index=True, use_container_width=True)
            with c3: st.markdown("**Top 5 Categories**"); st.dataframe(top_cats, hide_index=True, use_container_width=True)
            summary_excel = BytesIO()
            with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
                pd.DataFrame([{'Metric': 'Total Rejected', 'Value': len(rejected)}, {'Metric': 'Total Checked', 'Value': len(combined_df)}, {'Metric': 'Rejection Rate (%)', 'Value': (len(rejected)/len(combined_df)*100)}]).to_excel(writer, sheet_name='Summary', index=False)
                top_reasons.to_excel(writer, sheet_name='Top 5 Reasons', index=False)
                top_sellers.to_excel(writer, sheet_name='Top 5 Sellers', index=False)
                top_cats.to_excel(writer, sheet_name='Top 5 Categories', index=False)
            summary_excel.seek(0)
            st.download_button(label="📥 Download Summary Excel", data=summary_excel, file_name=f"Weekly_Analysis_Summary_{datetime.now().strftime('%Y-%m-%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
