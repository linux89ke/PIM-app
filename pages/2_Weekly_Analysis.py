import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import altair as alt

# --- CONFIG & UI ---
st.set_page_config(page_title="Weekly Analysis", layout="wide", page_icon="")

# Custom CSS for Infographic Style
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stMetricValue"] { color: #1f77b4; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title(" Weekly Insights Dashboard")


# --- UTILS ---
def get_top_stats(df, col, limit=5):
    """Returns top N counts for a column as a clean dataframe."""
    counts = df[col].value_counts().head(limit).reset_index()
    counts.columns = [col.replace('_', ' ').title(), 'Rejections']
    return counts

# --- FILE UPLOADER ---
weekly_files = st.file_uploader("Drop your 'Full Data' files here", accept_multiple_files=True, type=['xlsx', 'csv'])

if weekly_files:
    combined_df = pd.DataFrame()
    
    with st.spinner("Processing files..."):
        for f in weekly_files:
            try:
                f.seek(0)
                if f.name.endswith('.xlsx'):
                    try: df = pd.read_excel(f, sheet_name='ProductSets', dtype=str)
                    except: f.seek(0); df = pd.read_excel(f, dtype=str)
                else:
                    df = pd.read_csv(f, dtype=str)
                
                # Standardizing
                df.columns = df.columns.str.strip().str.upper()
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e:
                st.error(f"Error reading {f.name}: {e}")

    if not combined_df.empty:
        # Data Cleaning
        combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
        rejected = combined_df[combined_df['STATUS'].astype(str).str.upper() == 'REJECTED'].copy()
        
        # Calculations
        total_checked = len(combined_df)
        total_rejected = len(rejected)
        rej_rate = (total_rejected / total_checked * 100) if total_checked > 0 else 0

        # --- INFOGRAPHIC METRICS ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Checked", f"{total_checked:,}")
        m2.metric("Total Rejected", f"{total_rejected:,}", delta=f"{rej_rate:.1f}% Rate", delta_color="inverse")
        m3.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
        m4.metric("High-Risk Categories", f"{rejected['CATEGORY'].nunique():,}")

        st.divider()

        # --- CHARTS SECTION ---
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader(" Top Rejection Reasons")
            reason_data = get_top_stats(rejected, 'FLAG', 10)
            chart_reasons = alt.Chart(reason_data).mark_bar(cornerRadiusEnd=5).encode(
                x=alt.X('Rejections:Q', title="Number of Rejections"),
                y=alt.Y('Flag:N', sort='-x', title=None),
                color=alt.value('#FF4B4B'),
                tooltip=['Flag', 'Rejections']
            ).properties(height=350)
            st.altair_chart(chart_reasons, use_container_width=True)

        with col_right:
            st.subheader(" Top Rejected Sellers")
            seller_rej = get_top_stats(rejected, 'SELLER_NAME', 10)
            chart_sellers = alt.Chart(seller_rej).mark_bar(cornerRadiusEnd=5).encode(
                x=alt.X('Rejections:Q'),
                y=alt.Y('Seller Name:N', sort='-x', title=None),
                color=alt.value('#1F77B4'),
                tooltip=['Seller Name', 'Rejections']
            ).properties(height=350)
            st.altair_chart(chart_sellers, use_container_width=True)

        # --- DETAILED TABLES ---
        st.divider()
        st.subheader(" Top 5 Breakdown")
        t1, t2, t3 = st.columns(3)
        
        top5_reasons = get_top_stats(rejected, 'FLAG', 5)
        top5_sellers = get_top_stats(rejected, 'SELLER_NAME', 5)
        top5_cats = get_top_stats(rejected, 'CATEGORY', 5)

        t1.write("**Top 5 Flags**")
        t1.dataframe(top5_reasons, use_container_width=True, hide_index=True)
        t2.write("**Top 5 Sellers**")
        t2.dataframe(top5_sellers, use_container_width=True, hide_index=True)
        t3.write("**Top 5 Categories**")
        t3.dataframe(top5_cats, use_container_width=True, hide_index=True)

        # --- EXCEL EXPORT LOGIC ---
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Sheet 1: Executive Summary
            summary_df = pd.DataFrame({
                'Metric': ['Total Products Checked', 'Total Rejected', 'Rejection Rate %', 'Unique Sellers'],
                'Value': [total_checked, total_rejected, round(rej_rate, 2), combined_df['SELLER_NAME'].nunique()]
            })
            summary_df.to_excel(writer, sheet_name='Executive Summary', index=False)
            
            # Sheet 2: Top 5 Data
            top5_reasons.to_excel(writer, sheet_name='Top 5 Reasons', index=False)
            top5_sellers.to_excel(writer, sheet_name='Top 5 Sellers', index=False)
            top5_cats.to_excel(writer, sheet_name='Top 5 Categories', index=False)
            
            # Sheet 3: Full Rejections
            rejected.to_excel(writer, sheet_name='All Rejected Products', index=False)

        st.download_button(
            label=" Download Comprehensive Report (Excel)",
            data=output.getvalue(), # .getvalue() is critical for the fix
            file_name=f"Weekly_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
