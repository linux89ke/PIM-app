import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import altair as alt

# Import shared utilities
from streamlit_app import standardize_input_data

st.set_page_config(page_title="Weekly Analysis", layout="wide")

st.title("📈 Weekly Analysis Dashboard")

st.info("Upload multiple 'Full Data' files. The system aggregates them automatically.")

# 1. File Uploader
weekly_files = st.file_uploader(
    "Upload Full Data Files (XLSX/CSV)", 
    accept_multiple_files=True, 
    type=['xlsx', 'csv'], 
    key="weekly_files", 
    label_visibility="collapsed"
)

if weekly_files:
    combined_df = pd.DataFrame()
    
    # 2. Aggregation Logic
    with st.spinner(f"Aggregating {len(weekly_files)} files..."):
        for f in weekly_files:
            try:
                if f.name.endswith('.xlsx'):
                    try: df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                    except: f.seek(0); df = pd.read_excel(f, engine='openpyxl', dtype=str)
                else: 
                    df = pd.read_csv(f, dtype=str)
                
                df.columns = df.columns.str.strip()
                df = standardize_input_data(df)
                
                # Standardize columns
                for col in ['Status', 'Reason', 'FLAG', 'SELLER_NAME', 'CATEGORY', 'PRODUCT_SET_SID']:
                    if col not in df.columns: df[col] = pd.NA
                
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e: st.error(f"Error reading {f.name}: {e}")

    # 3. Main Analysis
    if not combined_df.empty:
        combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
        rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()

        # --- Metrics ---
        st.markdown("### Key Metrics")
        with st.container():
            m1, m2, m3, m4 = st.columns(4)
            total = len(combined_df)
            rej_count = len(rejected)
            rej_rate = (rej_count/total * 100) if total else 0
            
            m1.metric("Total Products", f"{total:,}")
            m2.metric("Total Rejected", f"{rej_count:,}")
            m3.metric("Rejection Rate", f"{rej_rate:.1f}%")
            m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
        st.markdown("---")

        # --- Deep Dive Data Preparation ---
        
        # A. Top 10 Sellers (with Top 3 Reasons)
        seller_deep_dive = []
        if not rejected.empty:
            top_10_sellers_series = rejected['SELLER_NAME'].value_counts().head(10)
            top_10_sellers_list = top_10_sellers_series.index.tolist() # Save list for SKU export later
            
            for seller, count in top_10_sellers_series.items():
                seller_data = rejected[rejected['SELLER_NAME'] == seller]
                top_flags = seller_data['FLAG'].value_counts().head(3)
                row = {'Seller Name': seller, 'Total Rejections': count}
                for i, (flag, f_count) in enumerate(top_flags.items(), 1):
                    row[f'Top Reason {i}'] = f"{flag} ({f_count})"
                seller_deep_dive.append(row)
        else:
            top_10_sellers_list = []
            
        df_seller_deep_dive = pd.DataFrame(seller_deep_dive)

        # B. Top 10 Reasons (Horizontal) & C. Top 10 Reasons (Vertical List)
        reason_deep_dive = []
        reason_vertical_list = []

        if not rejected.empty:
            top_10_reasons = rejected['FLAG'].value_counts().head(10)
            
            for reason, count in top_10_reasons.items():
                reason_data = rejected[rejected['FLAG'] == reason]
                top_sellers_for_reason = reason_data['SELLER_NAME'].value_counts().head(5)
                
                # Horizontal
                row_horiz = {'Reason (Flag)': reason, 'Total Count': count}
                for i, (seller, s_count) in enumerate(top_sellers_for_reason.items(), 1):
                    row_horiz[f'Top Seller {i}'] = f"{seller} ({s_count})"
                reason_deep_dive.append(row_horiz)

                # Vertical
                vertical_str = "\n".join([f"{seller} ({s_count})" for seller, s_count in top_sellers_for_reason.items()])
                row_vert = {
                    'Reason (Flag)': reason,
                    'Total Count': count,
                    'Top 5 Sellers List': vertical_str
                }
                reason_vertical_list.append(row_vert)
        
        df_reason_deep_dive = pd.DataFrame(reason_deep_dive)
        df_reason_vertical = pd.DataFrame(reason_vertical_list)

        # --- Display Tabs ---
        st.subheader("Deep Dive Analysis")
        tab1, tab2, tab3 = st.tabs(["Top Sellers Breakdown", "Top Reasons (Horizontal)", "Top Reasons (Vertical List)"])
        
        with tab1:
            st.markdown("**Top 10 Most Rejected Sellers & Their Primary Issues**")
            st.dataframe(df_seller_deep_dive, use_container_width=True, hide_index=True)
        with tab2:
            st.markdown("**Top 10 Rejection Reasons & Top Sellers (Spread)**")
            st.dataframe(df_reason_deep_dive, use_container_width=True, hide_index=True)
        with tab3:
            st.markdown("**Top 10 Rejection Reasons & Top Sellers (Vertical)**")
            st.dataframe(df_reason_vertical, use_container_width=True, hide_index=True, column_config={"Top 5 Sellers List": st.column_config.TextColumn("Top 5 Sellers", width="large")})

        # --- Download Section ---
        st.markdown("---")
        st.subheader("Downloads")
        
        col_d1, col_d2 = st.columns(2)

        # 1. Main Analysis Excel
        summary_excel = BytesIO()
        with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
            workbook = writer.book
            wrap_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
            
            # Summary Sheets
            pd.DataFrame([{'Metric': 'Total Rejected', 'Value': len(rejected)}, {'Metric': 'Rejection Rate (%)', 'Value': (len(rejected)/len(combined_df)*100)}]).to_excel(writer, sheet_name='Summary', index=False)
            
            if not df_seller_deep_dive.empty:
                df_seller_deep_dive.to_excel(writer, sheet_name='Sellers Breakdown', index=False)
                writer.sheets['Sellers Breakdown'].set_column(0, 5, 25)

            if not df_reason_deep_dive.empty:
                df_reason_deep_dive.to_excel(writer, sheet_name='Reasons (Horizontal)', index=False)
                writer.sheets['Reasons (Horizontal)'].set_column(0, 10, 20)

            if not df_reason_vertical.empty:
                df_reason_vertical.to_excel(writer, sheet_name='Reasons (Vertical)', index=False)
                writer.sheets['Reasons (Vertical)'].set_column('C:C', 50, wrap_format)

        summary_excel.seek(0)
        
        with col_d1:
            st.download_button(
                label="📥 Download Analysis Summary (Excel)",
                data=summary_excel,
                file_name=f"Weekly_Analysis_Summary_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # 2. Top Sellers SKU Dump (New Request)
        if not rejected.empty:
            # Filter rejected dataframe for only the top 10 sellers identified earlier
            sku_dump_df = rejected[rejected['SELLER_NAME'].isin(top_10_sellers_list)].copy()
            
            # Select only relevant columns for the SKU dump
            cols_to_keep = ['SELLER_NAME', 'PRODUCT_SET_SID', 'FLAG', 'Reason', 'CATEGORY']
            sku_dump_df = sku_dump_df[[c for c in cols_to_keep if c in sku_dump_df.columns]]
            
            # Sort for readability
            sku_dump_df = sku_dump_df.sort_values(by=['SELLER_NAME', 'FLAG'])
            
            sku_excel = BytesIO()
            with pd.ExcelWriter(sku_excel, engine='xlsxwriter') as writer:
                sku_dump_df.to_excel(writer, sheet_name='Top Sellers SKUs', index=False)
                writer.sheets['Top Sellers SKUs'].set_column('B:B', 20) # Widen SKU column
                writer.sheets['Top Sellers SKUs'].set_column('A:A', 20) # Widen Seller Name
            
            sku_excel.seek(0)
            
            with col_d2:
                st.download_button(
                    label="📑 Download SKUs for Top 10 Sellers",
                    data=sku_excel,
                    file_name=f"Top10_Sellers_Rejected_SKUs_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Contains raw list of Product IDs (SKUs) for only the top 10 most rejected sellers."
                )
