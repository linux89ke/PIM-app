import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import altair as alt

# Import shared utilities (Ensure this exists in your project)
try:
    from streamlit_app import standardize_input_data
except ImportError:
    # Fallback if the module is missing during testing
    def standardize_input_data(df): return df

st.set_page_config(page_title="Weekly Analysis", layout="wide")
st.title("📈 Weekly Analysis Dashboard")

st.info("Upload multiple 'Full Data' files exported from the Daily tab to see aggregated trends.")

weekly_files = st.file_uploader("Upload Full Data Files (XLSX/CSV)", 
                                accept_multiple_files=True, 
                                type=['xlsx', 'csv'], 
                                key="weekly_files")

if weekly_files:
    combined_df = pd.DataFrame()
    
    with st.spinner("Aggregating files..."):
        for f in weekly_files:
            try:
                # Reset file pointer for every read attempt
                f.seek(0)
                if f.name.endswith('.xlsx'):
                    try:
                        # Attempt to read specific sheet
                        df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                    except Exception:
                        # Fallback to first sheet
                        f.seek(0)
                        df = pd.read_excel(f, engine='openpyxl', dtype=str)
                else:
                    df = pd.read_csv(f, dtype=str)
                
                # Basic Cleanup
                df.columns = df.columns.str.strip()
                df = standardize_input_data(df)
                
                # Ensure essential columns exist to prevent KeyError
                essential_cols = ['Status', 'Reason', 'FLAG', 'SELLER_NAME', 'CATEGORY', 'PRODUCT_SET_SID']
                for col in essential_cols:
                    if col not in df.columns:
                        df[col] = "Unknown"
                
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e:
                st.error(f"Error reading {f.name}: {e}")

    if not combined_df.empty:
        # 1. Data Processing
        combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
        rejected = combined_df[combined_df['Status'].str.lower() == 'rejected'].copy()
        
        # 2. Metrics Row
        st.markdown("### Key Metrics")
        m1, m2, m3, m4 = st.columns(4)
        total = len(combined_df)
        rej_count = len(rejected)
        rej_rate = (rej_count / total * 100) if total > 0 else 0
        unique_sellers = combined_df['SELLER_NAME'].nunique()

        m1.metric("Total Products Checked", f"{total:,}")
        m2.metric("Total Rejected", f"{rej_count:,}")
        m3.metric("Rejection Rate", f"{rej_rate:.1f}%")
        m4.metric("Unique Sellers", f"{unique_sellers:,}")
        
        st.divider()

        # 3. Visualization Row 1
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Top Rejection Flags")
            if not rejected.empty:
                reason_counts = rejected['FLAG'].value_counts().reset_index().head(10)
                reason_counts.columns = ['Flag', 'Count']
                chart = alt.Chart(reason_counts).mark_bar().encode(
                    x='Count:Q',
                    y=alt.Y('Flag:N', sort='-x'),
                    color=alt.value('#FF6B6B'),
                    tooltip=['Flag', 'Count']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.write("No rejections found.")

        with c2:
            st.subheader("Top Rejected Categories")
            if not rejected.empty:
                cat_counts = rejected['CATEGORY'].value_counts().reset_index().head(10)
                cat_counts.columns = ['Category', 'Count']
                chart = alt.Chart(cat_counts).mark_bar().encode(
                    x='Count:Q',
                    y=alt.Y('Category:N', sort='-x'),
                    color=alt.value('#4ECDC4'),
                    tooltip=['Category', 'Count']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)

        # 4. Visualization Row 2
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Seller Trust Score (Lowest 10)")
            # Calculate trust score properly
            seller_stats = combined_df.groupby('SELLER_NAME').agg(
                Total=('PRODUCT_SET_SID', 'count'),
                Rejected=('Status', lambda x: (x.str.lower() == 'rejected').sum())
            )
            seller_stats['Trust Score'] = 100 - (seller_stats['Rejected'] / seller_stats['Total'] * 100)
            # Focus on sellers with rejections for the chart
            low_trust = seller_stats.sort_values(by='Rejected', ascending=False).head(10).reset_index()
            
            chart = alt.Chart(low_trust).mark_bar().encode(
                x=alt.X('SELLER_NAME:N', sort='-y', title="Seller"),
                y=alt.Y('Trust Score:Q', scale=alt.Scale(domain=[0, 100])),
                color=alt.Color('Trust Score:Q', scale=alt.Scale(scheme='redyellowgreen')),
                tooltip=['SELLER_NAME', 'Total', 'Rejected', 'Trust Score']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)

        with c4:
            st.subheader("Seller vs. Reason (Top 5 Sellers)")
            if not rejected.empty:
                top_seller_names = rejected['SELLER_NAME'].value_counts().head(5).index.tolist()
                filtered_rej = rejected[rejected['SELLER_NAME'].isin(top_seller_names)]
                breakdown = filtered_rej.groupby(['SELLER_NAME', 'Reason']).size().reset_index(name='Count')
                
                chart = alt.Chart(breakdown).mark_bar().encode(
                    x='SELLER_NAME:N',
                    y='Count:Q',
                    color='Reason:N',
                    tooltip=['SELLER_NAME', 'Reason', 'Count']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)

        # 5. Data Tables and Export
        st.divider()
        st.subheader("Summary Tables")
        
        if not rejected.empty:
            t1, t2, t3 = st.columns(3)
            top_reasons = rejected['FLAG'].value_counts().head(5).reset_index(name='Count')
            top_sellers = rejected['SELLER_NAME'].value_counts().head(5).reset_index(name='Rejections')
            top_cats = rejected['CATEGORY'].value_counts().head(5).reset_index(name='Rejections')
            
            t1.markdown("**Top 5 Reasons**")
            t1.dataframe(top_reasons, hide_index=True, use_container_width=True)
            t2.markdown("**Top 5 Sellers**")
            t2.dataframe(top_sellers, hide_index=True, use_container_width=True)
            t3.markdown("**Top 5 Categories**")
            t3.dataframe(top_cats, hide_index=True, use_container_width=True)

            # Excel Export Logic
            summary_excel = BytesIO()
            with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
                # Summary Sheet
                summary_data = pd.DataFrame([
                    {'Metric': 'Total Checked', 'Value': total},
                    {'Metric': 'Total Rejected', 'Value': rej_count},
                    {'Metric': 'Rejection Rate (%)', 'Value': round(rej_rate, 2)},
                    {'Metric': 'Unique Sellers', 'Value': unique_sellers}
                ])
                summary_data.to_excel(writer, sheet_name='General Summary', index=False)
                top_reasons.to_excel(writer, sheet_name='Top Reasons', index=False)
                top_sellers.to_excel(writer, sheet_name='Top Sellers', index=False)
                top_cats.to_excel(writer, sheet_name='Top Categories', index=False)
            
            st.download_button(
                label="📥 Download Summary Excel",
                data=summary_excel.getvalue(),
                file_name=f"Weekly_Analysis_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
