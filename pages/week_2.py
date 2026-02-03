import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import altair as alt

# Import shared utilities
from streamlit_app import standardize_input_data

st.set_page_config(page_title="Weekly Analysis", layout="wide")

st.title("📈 Weekly Analysis Dashboard")

st.info("Upload multiple 'Full Data' files exported from the Daily tab. The system handles large batches automatically.")

# 1. File Uploader (Accepts Multiple Files)
weekly_files = st.file_uploader(
    "Upload Full Data Files (XLSX/CSV)", 
    accept_multiple_files=True, 
    type=['xlsx', 'csv'], 
    key="weekly_files", 
    label_visibility="collapsed"
)

if weekly_files:
    combined_df = pd.DataFrame()
    
    # 2. Data Aggregation
    with st.spinner(f"Aggregating {len(weekly_files)} files..."):
        for f in weekly_files:
            try:
                # Handle Excel vs CSV
                if f.name.endswith('.xlsx'):
                    try: 
                        df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                    except: 
                        f.seek(0)
                        df = pd.read_excel(f, engine='openpyxl', dtype=str)
                else: 
                    df = pd.read_csv(f, dtype=str)
                
                # Standardization
                df.columns = df.columns.str.strip()
                df = standardize_input_data(df)
                
                # Ensure core columns exist
                required_cols = ['Status', 'Reason', 'FLAG', 'SELLER_NAME', 'CATEGORY', 'PRODUCT_SET_SID']
                for col in required_cols:
                    if col not in df.columns: 
                        df[col] = pd.NA
                
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e: 
                st.error(f"Error reading {f.name}: {e}")

    # 3. Main Analysis
    if not combined_df.empty:
        # Deduplicate based on ID to avoid counting the same product twice if uploaded in multiple files
        combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
        rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()

        # --- High Level Metrics ---
        st.markdown("### Key Metrics")
        with st.container():
            m1, m2, m3, m4 = st.columns(4)
            total = len(combined_df)
            rej_count = len(rejected)
            rej_rate = (rej_count/total * 100) if total else 0
            
            m1.metric("Total Products Checked", f"{total:,}")
            m2.metric("Total Rejected", f"{rej_count:,}")
            m3.metric("Rejection Rate", f"{rej_rate:.1f}%")
            m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
        
        st.markdown("---")

        # --- Visualizations (Existing) ---
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top Rejection Reasons (Flags)")
            if not rejected.empty and 'FLAG' in rejected.columns:
                reason_counts = rejected['FLAG'].value_counts().reset_index()
                reason_counts.columns = ['Flag', 'Count']
                chart = alt.Chart(reason_counts.head(10)).mark_bar().encode(
                    x=alt.X('Count'), 
                    y=alt.Y('Flag', sort='-x'), 
                    color=alt.value('#FF6B6B'), 
                    tooltip=['Flag', 'Count']
                ).interactive()
                st.altair_chart(chart, use_container_width=True)

        with c2:
            st.subheader("Top Rejected Categories")
            if not rejected.empty and 'CATEGORY' in rejected.columns:
                cat_counts = rejected['CATEGORY'].value_counts().reset_index()
                cat_counts.columns = ['Category', 'Count']
                chart = alt.Chart(cat_counts.head(10)).mark_bar().encode(
                    x=alt.X('Count'), 
                    y=alt.Y('Category', sort='-x'), 
                    color=alt.value('#4ECDC4'), 
                    tooltip=['Category', 'Count']
                ).interactive()
                st.altair_chart(chart, use_container_width=True)

        # --- Deep Dive Analysis (New Features) ---
        st.markdown("---")
        st.header("🔍 Deep Dive Analysis")

        # Logic 1: Top 10 Rejected Sellers & Their Top 3 Reasons
        seller_deep_dive = []
        if not rejected.empty:
            # Get Top 10 Sellers
            top_10_sellers = rejected['SELLER_NAME'].value_counts().head(10)
            
            for seller, count in top_10_sellers.items():
                # Filter for this seller
                seller_data = rejected[rejected['SELLER_NAME'] == seller]
                # Get Top 3 Flags for this seller
                top_flags = seller_data['FLAG'].value_counts().head(3)
                
                row = {
                    'Seller Name': seller,
                    'Total Rejections': count
                }
                # Flatten the top 3 reasons into the row
                for i, (flag, f_count) in enumerate(top_flags.items(), 1):
                    row[f'Top Reason {i}'] = f"{flag} ({f_count})"
                
                seller_deep_dive.append(row)
        
        df_seller_deep_dive = pd.DataFrame(seller_deep_dive)

        # Logic 2: Top 10 Rejected Reasons & Their Top 5 Sellers
        reason_deep_dive = []
        if not rejected.empty:
            # Get Top 10 Reasons (Flags)
            top_10_reasons = rejected['FLAG'].value_counts().head(10)
            
            for reason, count in top_10_reasons.items():
                # Filter for this reason
                reason_data = rejected[rejected['FLAG'] == reason]
                # Get Top 5 Sellers for this reason
                top_sellers_for_reason = reason_data['SELLER_NAME'].value_counts().head(5)
                
                row = {
                    'Reason (Flag)': reason,
                    'Total Count': count
                }
                # Flatten the top 5 sellers into the row
                for i, (seller, s_count) in enumerate(top_sellers_for_reason.items(), 1):
                    row[f'Top Seller {i}'] = f"{seller} ({s_count})"
                
                reason_deep_dive.append(row)
        
        df_reason_deep_dive = pd.DataFrame(reason_deep_dive)

        # Display Deep Dives
        tab1, tab2 = st.tabs(["Top 10 Sellers Breakdown", "Top 10 Reasons Breakdown"])
        
        with tab1:
            st.markdown("**Top 10 Most Rejected Sellers & Their Primary Issues**")
            st.dataframe(df_seller_deep_dive, use_container_width=True, hide_index=True)
            
        with tab2:
            st.markdown("**Top 10 Rejection Reasons & The Sellers Most Affected**")
            st.dataframe(df_reason_deep_dive, use_container_width=True, hide_index=True)

        # --- Download Logic ---
        st.markdown("---")
        st.subheader("Downloads")
        
        summary_excel = BytesIO()
        with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
            # Sheet 1: High Level Stats
            pd.DataFrame([
                {'Metric': 'Total Rejected', 'Value': len(rejected)},
                {'Metric': 'Total Checked', 'Value': len(combined_df)},
                {'Metric': 'Rejection Rate (%)', 'Value': (len(rejected)/len(combined_df)*100)}
            ]).to_excel(writer, sheet_name='Summary', index=False)
            
            # Sheet 2: Top 5 Summaries (Simple)
            if not rejected.empty:
                rejected['FLAG'].value_counts().head(5).reset_index(name='Count').to_excel(writer, sheet_name='Top 5 Reasons', index=False)
                rejected['SELLER_NAME'].value_counts().head(5).reset_index(name='Count').to_excel(writer, sheet_name='Top 5 Sellers', index=False)
                rejected['CATEGORY'].value_counts().head(5).reset_index(name='Count').to_excel(writer, sheet_name='Top 5 Categories', index=False)
            
            # Sheet 3: Deep Dive - Sellers (The new request)
            if not df_seller_deep_dive.empty:
                df_seller_deep_dive.to_excel(writer, sheet_name='Deep Dive - Sellers', index=False)
                # Auto-adjust column width logic (optional polish)
                worksheet = writer.sheets['Deep Dive - Sellers']
                for idx, col in enumerate(df_seller_deep_dive):
                    max_len = max(df_seller_deep_dive[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(idx, idx, max_len)

            # Sheet 4: Deep Dive - Reasons (The new request)
            if not df_reason_deep_dive.empty:
                df_reason_deep_dive.to_excel(writer, sheet_name='Deep Dive - Reasons', index=False)
                worksheet = writer.sheets['Deep Dive - Reasons']
                for idx, col in enumerate(df_reason_deep_dive):
                    max_len = max(df_reason_deep_dive[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(idx, idx, max_len)

        summary_excel.seek(0)
        
        st.download_button(
            label="📥 Download Comprehensive Analysis (Excel)",
            data=summary_excel,
            file_name=f"Weekly_Analysis_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Includes General Summary, Deep Dive on Sellers, and Deep Dive on Reasons."
        )
