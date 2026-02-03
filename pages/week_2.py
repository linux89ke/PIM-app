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
            top_10_sellers = rejected['SELLER_NAME'].value_counts().head(10)
            for seller, count in top_10_sellers.items():
                seller_data = rejected[rejected['SELLER_NAME'] == seller]
                top_flags = seller_data['FLAG'].value_counts().head(3)
                row = {'Seller Name': seller, 'Total Rejections': count}
                for i, (flag, f_count) in enumerate(top_flags.items(), 1):
                    row[f'Top Reason {i}'] = f"{flag} ({f_count})"
                seller_deep_dive.append(row)
        df_seller_deep_dive = pd.DataFrame(seller_deep_dive)

        # B. Top 10 Reasons (with Top 5 Sellers - Horizontal Columns)
        reason_deep_dive = []
        # C. Top 10 Reasons (with Top 5 Sellers - Vertical List) << NEW REQUEST
        reason_vertical_list = []

        if not rejected.empty:
            top_10_reasons = rejected['FLAG'].value_counts().head(10)
            
            for reason, count in top_10_reasons.items():
                reason_data = rejected[rejected['FLAG'] == reason]
                top_sellers_for_reason = reason_data['SELLER_NAME'].value_counts().head(5)
                
                # Logic for Horizontal Table
                row_horiz = {'Reason (Flag)': reason, 'Total Count': count}
                for i, (seller, s_count) in enumerate(top_sellers_for_reason.items(), 1):
                    row_horiz[f'Top Seller {i}'] = f"{seller} ({s_count})"
                reason_deep_dive.append(row_horiz)

                # Logic for Vertical List Table (New)
                # Create a string joined by newlines
                vertical_str_list = [f"{seller} ({s_count})" for seller, s_count in top_sellers_for_reason.items()]
                vertical_str = "\n".join(vertical_str_list)
                
                row_vert = {
                    'Reason (Flag)': reason,
                    'Total Count': count,
                    'Top 5 Sellers List': vertical_str  # This puts them all in one cell
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
            st.markdown("**Top 10 Rejection Reasons & Top Sellers (Spread columns)**")
            st.dataframe(df_reason_deep_dive, use_container_width=True, hide_index=True)

        with tab3:
            st.markdown("**Top 10 Rejection Reasons & Top Sellers (Vertical List)**")
            st.info("This view groups sellers into a single column. This format is preserved in the Excel download.")
            st.dataframe(
                df_reason_vertical, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Top 5 Sellers List": st.column_config.TextColumn("Top 5 Sellers", width="large")
                }
            )

        # --- Download Logic ---
        summary_excel = BytesIO()
        with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Format to enable text wrapping for the vertical list
            wrap_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})

            # 1. Summary Sheet
            pd.DataFrame([
                {'Metric': 'Total Rejected', 'Value': len(rejected)},
                {'Metric': 'Rejection Rate (%)', 'Value': (len(rejected)/len(combined_df)*100)}
            ]).to_excel(writer, sheet_name='Summary', index=False)

            # 2. Deep Dive - Sellers
            if not df_seller_deep_dive.empty:
                df_seller_deep_dive.to_excel(writer, sheet_name='Sellers Breakdown', index=False)
                # Auto-width
                worksheet = writer.sheets['Sellers Breakdown']
                for idx, col in enumerate(df_seller_deep_dive):
                    max_len = max(df_seller_deep_dive[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(idx, idx, max_len)

            # 3. Deep Dive - Reasons (Horizontal)
            if not df_reason_deep_dive.empty:
                df_reason_deep_dive.to_excel(writer, sheet_name='Reasons (Horizontal)', index=False)
                worksheet = writer.sheets['Reasons (Horizontal)']
                for idx, col in enumerate(df_reason_deep_dive):
                    max_len = max(df_reason_deep_dive[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(idx, idx, max_len)

            # 4. Deep Dive - Reasons (Vertical List) - NEW
            if not df_reason_vertical.empty:
                sheet_name = 'Reasons (Vertical)'
                df_reason_vertical.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                
                # Apply text wrap to the 3rd column (Index 2: 'Top 5 Sellers List')
                # We assume column C is the sellers list
                worksheet.set_column('A:A', 30) # Reason width
                worksheet.set_column('B:B', 15) # Count width
                worksheet.set_column('C:C', 50, wrap_format) # Sellers width + Wrap Text

        summary_excel.seek(0)
        
        st.markdown("---")
        st.download_button(
            label="📥 Download Excel Analysis",
            data=summary_excel,
            file_name=f"Weekly_Analysis_Full_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
